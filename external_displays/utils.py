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

from Xlib import display as xdisplay

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
            'org.freedesktop.systemd1',
            '/org/freedesktop/systemd1',
            'org.freedesktop.systemd1.Manager',
            None
        )

        unit_path = systemd_object.call_sync(
            'GetUnit',
            GLib.Variant('(s)', (service_name,)),
            Gio.DBusCallFlags.NONE,
            -1,
            None
        ).unpack()[0]

        unit_object = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.systemd1',
            unit_path,
            'org.freedesktop.systemd1.Unit',
            None
        )

        active_state = unit_object.get_cached_property('ActiveState').get_string()
        return active_state == 'active'
    except GLib.Error as e:
        if 'NoSuchUnit' in str(e):
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
            'org.freedesktop.systemd1',
            '/org/freedesktop/systemd1',
            'org.freedesktop.systemd1.Manager',
            None
        )

        systemd_object.call_sync(
            'StartUnit',
            GLib.Variant('(ss)', (service_name, 'replace')),
            Gio.DBusCallFlags.NONE,
            -1,
            None
        )
        return True
    except GLib.Error as e:
        print(f"Error starting {service_name}: {e}")
        return False

def stop_service(service_name, system_bus=False):
    """Stop a systemd service using D-Bus"""
    try:
        bus = get_systemd_bus(system_bus)
        systemd_object = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.systemd1',
            '/org/freedesktop/systemd1',
            'org.freedesktop.systemd1.Manager',
            None
        )

        systemd_object.call_sync(
            'StopUnit',
            GLib.Variant('(ss)', (service_name, 'replace')),
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
        if display_info.get('status') == 'connected':
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

def get_display_modes(card_path, connector):
    modes_path = f"/sys/class/drm/{card_path}/{card_path}-{connector}/modes"
    if os.path.exists(modes_path):
        try:
            with open(modes_path, "r") as f:
                modes = [line.strip() for line in f.readlines()]
            # Deduplicate the list
            unique_modes = []
            for mode in modes:
                if mode not in unique_modes:
                    unique_modes.append(mode)
            return unique_modes
        except Exception as e:
            print(f"Error reading modes: {e}")
    return []

def get_current_resolution(connector, target_display=None):
    try:
        d = xdisplay.Display(target_display or os.environ.get("DISPLAY"))
        screen = d.screen()
        root = screen.root

        if not hasattr(d, "randr_version"):
            return f"{screen.width_in_pixels}x{screen.height_in_pixels}"

        resources = root.xrandr_get_screen_resources()

        for output in resources.outputs:
            output_info = d.xrandr_get_output_info(output, resources.config_timestamp)
            if output_info.connection != 0:  # 0 is Connected
                continue

            output_name = output_info.name
            if connector in output_name and output_info.crtc:
                crtc_info = d.xrandr_get_crtc_info(output_info.crtc, resources.config_timestamp)
                return f"{crtc_info.width}x{crtc_info.height}"

        return None
    except Exception as e:
        print(f"Error getting current resolution with Xlib: {e}")
        return None

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
