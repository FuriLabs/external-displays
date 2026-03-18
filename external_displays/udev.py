# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import threading

import pyudev

class UDevMonitor:
    def __init__(self, callback=None):
        self.callback = callback
        self.context = pyudev.Context()
        self.monitor = None
        self.observer = None
        self.lock = threading.Lock()

    def safe_attr(self, device: pyudev.Device, key: str, default: str = "") -> str:
        value = device.get(key)
        return value if value is not None else default

    def safe_bool_attr(self, device: pyudev.Device, key: str) -> bool:
        value = device.get(key)
        if value is None:
            return False
        return str(value).strip() not in ("", "0", "false", "False", "no", "No")

    def device_info(self, device: pyudev.Device) -> dict:
        subsystem = device.subsystem or ""
        device_node = device.device_node or ""

        is_usb = subsystem == "usb" and (device.device_type or "") == "usb_device"
        is_input_event = subsystem == "input" and device_node.startswith("/dev/input/event")

        return {
            "kind": "usb" if is_usb else "input" if is_input_event else "other",
            "action": device.action or "",
            "device_node": device_node,
            "device_path": device.device_path or "",
            "device_type": device.device_type or "",
            "subsystem": subsystem,
            "sys_name": getattr(device, "sys_name", "") or "",
            "sys_number": getattr(device, "sys_number", "") or "",
            "vendor_id": self.safe_attr(device, "ID_VENDOR_ID"),
            "model_id": self.safe_attr(device, "ID_MODEL_ID"),
            "vendor": self.safe_attr(device, "ID_VENDOR_FROM_DATABASE") or self.safe_attr(device, "ID_VENDOR"),
            "model": self.safe_attr(device, "ID_MODEL_FROM_DATABASE") or self.safe_attr(device, "ID_MODEL"),
            "serial": self.safe_attr(device, "ID_SERIAL_SHORT") or self.safe_attr(device, "ID_SERIAL"),
            "busnum": self.safe_attr(device, "BUSNUM"),
            "devnum": self.safe_attr(device, "DEVNUM"),
            "devpath": self.safe_attr(device, "DEVPATH"),
            "name": self.safe_attr(device, "NAME"),
            "id_input": self.safe_bool_attr(device, "ID_INPUT"),
            "id_input_keyboard": self.safe_bool_attr(device, "ID_INPUT_KEYBOARD"),
            "id_input_mouse": self.safe_bool_attr(device, "ID_INPUT_MOUSE"),
            "id_input_touchpad": self.safe_bool_attr(device, "ID_INPUT_TOUCHPAD"),
            "id_input_touchscreen": self.safe_bool_attr(device, "ID_INPUT_TOUCHSCREEN"),
            "id_input_tablet": self.safe_bool_attr(device, "ID_INPUT_TABLET"),
        }

    def is_relevant_event(self, device: pyudev.Device) -> bool:
        subsystem = device.subsystem or ""
        device_type = device.device_type or ""
        device_node = device.device_node or ""

        if subsystem == "usb" and device_type == "usb_device":
            return True

        if subsystem == "input" and device_node.startswith("/dev/input/event"):
            return True

        return False

    def emit(self, device: pyudev.Device) -> None:
        if not self.is_relevant_event(device):
            return

        if self.callback is None:
            return

        action = device.action or ""
        info = self.device_info(device)
        self.callback(action, info)

    def on_udev_event(self, device: pyudev.Device) -> None:
        self.emit(device)

    def start(self) -> None:
        with self.lock:
            if self.observer is not None:
                return

            self.monitor = pyudev.Monitor.from_netlink(self.context)

            self.observer = pyudev.MonitorObserver(
                self.monitor,
                callback=self.on_udev_event,
                name="udev-monitor",
            )
            self.observer.start()

    def stop(self) -> None:
        with self.lock:
            if self.observer is not None:
                try:
                    self.observer.stop()
                except Exception:
                    pass
                self.observer = None

            self.monitor = None

    def list_usb_devices(self) -> list[dict]:
        devices = []

        for device in self.context.list_devices(subsystem="usb", DEVTYPE="usb_device"):
            devices.append(self.device_info(device))

        return devices

    def is_device_connected(self, matcher) -> bool:
        for info in self.list_usb_devices():
            try:
                if matcher(info):
                    return True
            except Exception:
                continue
        return False
