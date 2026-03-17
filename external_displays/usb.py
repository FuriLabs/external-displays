# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import threading

import pyudev

class USBMonitor:
    def __init__(self, callback=None):
        self.callback = callback
        self.context = pyudev.Context()
        self.monitor = None
        self.observer = None
        self._lock = threading.Lock()

    @staticmethod
    def _safe_attr(device: pyudev.Device, key: str, default: str = "") -> str:
        value = device.get(key)
        return value if value is not None else default

    def _device_info(self, device: pyudev.Device) -> dict:
        return {
            "action": device.action or "",
            "device_node": device.device_node or "",
            "device_path": device.device_path or "",
            "device_type": device.device_type or "",
            "subsystem": device.subsystem or "",
            "vendor_id": self._safe_attr(device, "ID_VENDOR_ID"),
            "model_id": self._safe_attr(device, "ID_MODEL_ID"),
            "vendor": self._safe_attr(device, "ID_VENDOR_FROM_DATABASE") or self._safe_attr(device, "ID_VENDOR"),
            "model": self._safe_attr(device, "ID_MODEL_FROM_DATABASE") or self._safe_attr(device, "ID_MODEL"),
            "serial": self._safe_attr(device, "ID_SERIAL_SHORT") or self._safe_attr(device, "ID_SERIAL"),
            "busnum": self._safe_attr(device, "BUSNUM"),
            "devnum": self._safe_attr(device, "DEVNUM"),
            "devpath": self._safe_attr(device, "DEVPATH"),
        }

    def _emit(self, device: pyudev.Device) -> None:
        if device.subsystem != "usb" or device.device_type != "usb_device":
            return

        if self.callback is None:
            return

        action = device.action or ""
        info = self._device_info(device)
        self.callback(action, info)

    def _on_udev_event(self, device: pyudev.Device) -> None:
        self._emit(device)

    def start(self) -> None:
        with self._lock:
            if self.observer is not None:
                return

            self.monitor = pyudev.Monitor.from_netlink(self.context)
            self.monitor.filter_by(subsystem="usb")

            self.observer = pyudev.MonitorObserver(
                self.monitor,
                callback=self._on_udev_event,
                name="usb-monitor",
            )
            self.observer.start()

    def stop(self) -> None:
        with self._lock:
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
            devices.append(self._device_info(device))

        return devices

    def is_device_connected(self, matcher) -> bool:
        for info in self.list_usb_devices():
            try:
                if matcher(info):
                    return True
            except Exception:
                continue
        return False
