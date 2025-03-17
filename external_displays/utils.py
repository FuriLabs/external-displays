# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2025 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import os
import time
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
