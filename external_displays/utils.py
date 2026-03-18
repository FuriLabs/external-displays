# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import os
import time
import re
import glob
import gi
from gi.repository import Gio, GLib

from external_displays.edid import get_display_info

def get_systemd_bus(system_bus=False):
    if system_bus:
        return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    else:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)

def check_service_status(service_name, system_bus=False):
    try:
        bus = get_systemd_bus(system_bus)
        systemd_object = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            None
        )

        unit_path = systemd_object.call_sync(
            "GetUnit",
            GLib.Variant("(s)", (service_name,)),
            Gio.DBusCallFlags.NONE,
            -1,
            None
        ).unpack()[0]

        unit_object = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.systemd1",
            unit_path,
            "org.freedesktop.systemd1.Unit",
            None
        )

        active_state = unit_object.get_cached_property("ActiveState").get_string()
        return active_state == "active"
    except GLib.Error as e:
        if "NoSuchUnit" in str(e):
            return False
        print(f"Error checking {service_name} status: {e}")
        return False

def start_service(service_name, system_bus=False):
    try:
        bus = get_systemd_bus(system_bus)
        systemd_object = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            None
        )

        systemd_object.call_sync(
            "StartUnit",
            GLib.Variant("(ss)", (service_name, "replace")),
            Gio.DBusCallFlags.NONE,
            -1,
            None
        )
        return True
    except GLib.Error as e:
        print(f"Error starting {service_name}: {e}")
        return False

def stop_service(service_name, system_bus=False):
    try:
        bus = get_systemd_bus(system_bus)
        systemd_object = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            None
        )

        systemd_object.call_sync(
            "StopUnit",
            GLib.Variant("(ss)", (service_name, "replace")),
            Gio.DBusCallFlags.NONE,
            -1,
            None
        )
        return True
    except GLib.Error as e:
        print(f"Error stopping {service_name}: {e}")
        return False

def wait_for_file(path, timeout=30):
    start_time = time.time()
    while not os.path.exists(path):
        if time.time() - start_time > timeout:
            return False
        time.sleep(0.5)
    return True

def wait_for_display_connected(card_path, connector, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        display_info = get_display_info(card_path, connector)
        if display_info.get("status") == "connected":
            return True
        time.sleep(1)
    return False

def detect_connector(card_path):
    default_connector = "DVI-I-1"
    default_path = f"/sys/class/drm/{card_path}/{card_path}-{default_connector}"

    if os.path.exists(default_path):
        return default_connector

    pattern = f"/sys/class/drm/{card_path}/{card_path}-DVI-I-*"
    matching_paths = glob.glob(pattern)

    if matching_paths:
        basename = os.path.basename(matching_paths[0])
        connector = basename.split("-", 1)[1]
        print(f"Default connector not found. Using: {connector}")
        return connector

    print(f"No DVI-I connectors found. Falling back to default: {default_connector}")
    return default_connector

def get_sysfs_event_name(by_id_name, real_path):
    name = None
    try:
        base = os.path.basename(real_path)
        name_path = f"/sys/class/input/{base}/device/name"
        if os.path.exists(name_path):
            with open(name_path, "r", encoding="utf-8", errors="ignore") as f:
                name = f.read().strip()
    except Exception as e:
        print(f"Error reading sysfs name for {real_path}: {e}")

    base_label = name or by_id_name

    match = re.search(r"-if(\d+)", by_id_name)

    if match:
        interface_number = match.group(1)
        return f"{base_label} (if{interface_number})"

    return base_label

def get_ignored_input_events(ignore_file="/usr/lib/furios/device/input-redirector-ignore"):
    ignored = set()

    try:
        if not os.path.exists(ignore_file):
            return ignored

        with open(ignore_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()

        if not content:
            return ignored

        for entry in content.split(","):
            entry = entry.strip()
            if re.fullmatch(r"event\d+", entry):
                ignored.add(entry)
    except Exception as e:
        print(f"Error reading ignored input events from {ignore_file}: {e}")

    return ignored

def get_input_device_candidates(ignore_file="/usr/lib/furios/device/input-redirector-ignore"):
    devices = []
    seen_real_paths = set()
    ignored_events = get_ignored_input_events(ignore_file)

    # persistent by-id devices
    by_id_path = "/dev/input/by-id"
    try:
        if os.path.exists(by_id_path):
            for device in sorted(os.listdir(by_id_path)):
                if "event" not in device:
                    continue

                symlink_path = os.path.join(by_id_path, device)

                try:
                    real_path = os.path.realpath(symlink_path)
                    event_name = os.path.basename(real_path)

                    if not re.fullmatch(r"event\d+", event_name):
                        continue

                    if event_name in ignored_events:
                        continue

                    friendly = get_sysfs_event_name(device, real_path)

                    devices.append((friendly, real_path))
                    seen_real_paths.add(real_path)
                except Exception as e:
                    print(f"Error processing by-id device {symlink_path}: {e}")
                    continue
    except Exception as e:
        print(f"Error scanning {by_id_path}: {e}")

    # raw event devices not already covered by by-id
    try:
        for real_path in sorted(glob.glob("/dev/input/event*")):
            try:
                event_name = os.path.basename(real_path)

                if event_name in ignored_events:
                    continue

                if real_path in seen_real_paths:
                    continue

                name_path = f"/sys/class/input/{event_name}/device/name"
                if os.path.exists(name_path):
                    with open(name_path, "r", encoding="utf-8", errors="ignore") as f:
                        friendly = f.read().strip()
                else:
                    friendly = event_name

                devices.append((friendly, real_path))
                seen_real_paths.add(real_path)
            except Exception as e:
                print(f"Error processing event device {real_path}: {e}")
                continue
    except Exception as e:
        print(f"Error scanning raw event devices: {e}")

    return devices

def set_gnome_wm_preference(value):
    try:
        settings = Gio.Settings.new("org.gnome.desktop.wm.preferences")
        settings.set_string("button-layout", value)
        return True
    except Exception as e:
        print(f"Failed to set gsettings org.gnome.desktop.wm.preferences button-layout='{value}': {e}")
        return False

def set_input_redirector_display(target_display):
    try:
        settings = Gio.Settings.new("io.furios.input-redirector")
        settings.set_string("display", target_display)
        return True
    except Exception as e:
        print(f"Failed to set input redirector display: {e}")
        return False

def set_input_redirector_input_paths(value):
    try:
        settings = Gio.Settings.new("io.furios.input-redirector")
        settings.set_string("input-paths", value)
        return True
    except Exception as e:
        print(f"Failed to set input redirector input paths: {e}")
        return False

def get_input_redirector_input_paths():
    try:
        settings = Gio.Settings.new("io.furios.input-redirector")
        value = settings.get_string("input-paths")
        return set(value.split(",")) if value else set()
    except Exception as e:
        print(f"Error reading input redirector input paths: {e}")
        return set()

def set_power_profile_overdrive(enabled):
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

        pp_proxy = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.UPower.PowerProfiles",
            "/org/freedesktop/UPower/PowerProfiles",
            "org.freedesktop.UPower.PowerProfiles",
            None,
        )

        pp_proxy.call_sync(
            "EnableOverdrive",
            GLib.Variant("(b)", (bool(enabled),)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

        return True
    except Exception as e:
        print(f"Failed to set power profile overdrive: {e}")
        return False

def get_osk_proxy(osk_proxy):
    if osk_proxy is not None:
        return osk_proxy

    try:
        osk_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            "sm.puri.OSK0",
            "/sm/puri/OSK0",
            "sm.puri.OSK0",
            None,
        )
    except Exception as e:
        print(f"Failed to create OSK proxy: {e}")
        osk_proxy = None

    return osk_proxy

def set_osk_visible(osk_proxy, visible):
    proxy = get_osk_proxy(osk_proxy)

    if proxy is None:
        return False, osk_proxy

    try:
        proxy.call_sync(
            "SetVisible",
            GLib.Variant("(b)", (visible,)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return True, proxy
    except Exception as e:
        print(f"Failed to set OSK visibility: {e}")
        return False, proxy
