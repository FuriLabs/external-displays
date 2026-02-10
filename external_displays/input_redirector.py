# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BUS_NAME = "io.furios.InputRedirector"
OBJ_PATH = "/io/furios/InputRedirector"
IFACE = "io.furios.InputRedirector"

class InputRedirector:
    def __init__(self, source="app:external-displays"):
        self.source = source
        self._proxy = None
        self.connect()

    def connect(self):
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                None,
                BUS_NAME,
                OBJ_PATH,
                IFACE,
                None,
            )
        except Exception as e:
            print(f"InputRedirector: failed to create D-Bus proxy: {e}")
            self._proxy = None

    def dbus_call(self, method, params):
        if self._proxy is None:
            self.connect()
            if self._proxy is None:
                return None

        try:
            return self._proxy.call_sync(
                method,
                params,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except Exception as e:
            # Service may have restarted. try one reconnect next time.
            print(f"InputRedirector: D-Bus call {method} failed: {e}")
            self._proxy = None
            return None

    def key_event_code(self, evdev_code: int, value: int):
        self.dbus_call("KeyEvent", GLib.Variant("(uis)", (int(evdev_code), int(value), self.source)))

    def mouse_button(self, code: int, value: int):
        self.dbus_call("MouseButton", GLib.Variant("(uis)", (int(code), int(value), self.source)))

    def mouse_motion(self, dx: int, dy: int):
        self.dbus_call("MouseMotion", GLib.Variant("(iis)", (int(dx), int(dy), self.source)))

    def scroll(self, code: int, value: int):
        self.dbus_call("Scroll", GLib.Variant("(uis)", (int(code), int(value), self.source)))

    def touch_down(self, x: int, y: int):
        self.dbus_call("TouchDown", GLib.Variant("(iis)", (int(x), int(y), self.source)))

    def touch_move(self, x: int, y: int):
        self.dbus_call("TouchMove", GLib.Variant("(iis)", (int(x), int(y), self.source)))

    def touch_up(self):
        self.dbus_call("TouchUp", GLib.Variant("(s)", (self.source,)))

    def get_screen_size(self):
        ret = self.dbus_call("GetScreenSize", None)
        if ret is None:
            return 0, 0
        try:
            width, height = ret.unpack()
            return int(width), int(height)
        except Exception:
            return 0, 0
