# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import os
import socket
import struct

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BUS_NAME = "io.furios.InputRedirector"
OBJ_PATH = "/io/furios/InputRedirector"
IFACE = "io.furios.InputRedirector"

IR_EVENT_VERSION = 1

IR_EV_KEY = 1
IR_EV_MOUSE_BUTTON = 2
IR_EV_MOUSE_MOTION = 3
IR_EV_SCROLL = 4
IR_EV_TOUCH_DOWN = 5
IR_EV_TOUCH_MOVE = 6
IR_EV_TOUCH_UP = 7

# struct __attribute__((packed)) {
#     guint16 version;
#     guint16 type;
#     gint32 a;
#     gint32 b;
#     guint32 code;
#     gint32 value;
# }
EVENT_STRUCT = struct.Struct("=HHiiIi")

class InputRedirector:
    def __init__(self, source="app:external-displays"):
        self.source = source
        self.proxy = None
        self.sock = None
        self.connect()

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

        self.proxy = None

    def connect(self):
        self.close()

        try:
            self.proxy = Gio.DBusProxy.new_for_bus_sync(
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
            self.proxy = None
            return

        self.open_input_channel()

    def open_input_channel(self):
        if self.proxy is None:
            return

        try:
            ret, out_fd_list = self.proxy.call_with_unix_fd_list_sync(
                "OpenInputChannel",
                GLib.Variant("(s)", (self.source,)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )

            handle_index = ret.unpack()[0]
            recv_fd = out_fd_list.get(handle_index)

            real_fd = os.dup(recv_fd)
            self.sock = socket.socket(fileno=real_fd)
        except Exception as e:
            print(f"InputRedirector: failed to open fast input channel: {e}")
            self.sock = None

    def dbus_call(self, method, params):
        if self.proxy is None:
            self.connect()
            if self.proxy is None:
                return None

        try:
            return self.proxy.call_sync(
                method,
                params,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except Exception as e:
            # Service may have restarted. try one reconnect next time.
            print(f"InputRedirector: D-Bus call {method} failed: {e}")
            self.proxy = None
            self.close()
            return None

    def send_socket_event(self, ev_type: int, a: int = 0, b: int = 0, code: int = 0, value: int = 0) -> bool:
        if self.sock is None:
            if self.proxy is None:
                self.connect()
            elif self.sock is None:
                self.open_input_channel()

        if self.sock is None:
            return False

        try:
            payload = EVENT_STRUCT.pack(
                int(IR_EVENT_VERSION),
                int(ev_type),
                int(a),
                int(b),
                int(code),
                int(value),
            )
            self.sock.sendall(payload)
            return True
        except Exception as e:
            print(f"InputRedirector: socket send failed: {e}")
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            return False

    def key_event_code(self, evdev_code: int, value: int):
        if self.send_socket_event(IR_EV_KEY, code=int(evdev_code), value=int(value)):
            return

        self.dbus_call("KeyEvent", GLib.Variant("(uis)", (int(evdev_code), int(value), self.source)))

    def mouse_button(self, code: int, value: int):
        if self.send_socket_event(IR_EV_MOUSE_BUTTON, code=int(code), value=int(value)):
            return

        self.dbus_call("MouseButton", GLib.Variant("(uis)", (int(code), int(value), self.source)))

    def mouse_motion(self, dx: int, dy: int):
        if self.send_socket_event(IR_EV_MOUSE_MOTION, a=int(dx), b=int(dy)):
            return

        self.dbus_call("MouseMotion", GLib.Variant("(iis)", (int(dx), int(dy), self.source)))

    def scroll(self, code: int, value: int):
        if self.send_socket_event(IR_EV_SCROLL, code=int(code), value=int(value)):
            return

        self.dbus_call("Scroll", GLib.Variant("(uis)", (int(code), int(value), self.source)))

    def touch_down(self, x: int, y: int):
        if self.send_socket_event(IR_EV_TOUCH_DOWN, a=int(x), b=int(y)):
            return

        self.dbus_call("TouchDown", GLib.Variant("(iis)", (int(x), int(y), self.source)))

    def touch_move(self, x: int, y: int):
        if self.send_socket_event(IR_EV_TOUCH_MOVE, a=int(x), b=int(y)):
            return

        self.dbus_call("TouchMove", GLib.Variant("(iis)", (int(x), int(y), self.source)))

    def touch_up(self):
        if self.send_socket_event(IR_EV_TOUCH_UP):
            return

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
