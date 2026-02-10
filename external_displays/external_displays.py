# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import gi
import os
import glob
import threading
import subprocess

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw, Gio

from Xlib import display

from external_displays.edid import get_display_info
from external_displays.keyboard_emulator import KeyboardEmulator
from external_displays.touch_mouse_emulator import TouchMouseEmulator
from external_displays.utils import (
    check_service_status,
    start_service,
    stop_service,
    wait_for_file,
    wait_for_display_connected,
)

from external_displays import ui

class ExternalDisplays(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect("activate", self.on_activate)

        # Display and hardware configuration
        self.target_display = os.environ.get("DISPLAY", ":1")
        self.card_path = "card1"
        self.connector = self.detect_connector()
        self.enable_file_path = os.path.expanduser("~/.enable_external_display")

        # Input device management
        self.input_device_buttons = []
        self.input_device_rows = []

        # Display mode management
        self.mode_radio_buttons = {}
        self.mode_radio_handlers = {}

        # Flag to track if focus regain is active
        self.focus_regain_active = False
        self.focus_regain_source_id = None

        # UI widgets (will be initialized in on_activate)
        self.win = None
        self.toast_overlay = None
        self.toolbar_view = None
        self.header_bar = None
        self.bottom_sheet = None
        self.stack = None
        self.config_page = None
        self.input_page = None
        self.drawing_area = None
        self.status_label = None

        # Settings sheet
        self.sensitivity_slider = None
        self.display_entry = None
        self.connector_entry = None
        self.card_entry = None
        self.apply_button = None

        # Switches and controls
        self.display_services_switch = None

        # Labels for display info
        self.status_value = None
        self.power_value = None
        self.mfg_value = None
        self.display_info_labels = {}

        # Expander rows
        self.modes_expander = None
        self.inputs_expander = None

        # Emulators
        self.keyboard_emulator = None
        self.touch_mouse_emulator = None

        # Controllers
        self.key_controller = None
        self.config_page_key_controller = None

        # Refresh timer
        self.refresh_timeout_id = None

        # Progress dialog
        self.progress_dialog = None

        # Display service status
        self.display_enabled = False

    def set_gnome_wm_preference(self, value):
        try:
            settings = Gio.Settings.new("org.gnome.desktop.wm.preferences")
            settings.set_string("button-layout", value)
            return True
        except Exception as e:
            print(f"Failed to set gsettings org.gnome.desktop.wm.preferences button-layout='{value}': {e}")
            return False

    def detect_connector(self):
        default_connector = "DVI-I-1"
        default_path = f"/sys/class/drm/{self.card_path}/{self.card_path}-{default_connector}"

        if os.path.exists(default_path):
            return default_connector

        pattern = f"/sys/class/drm/{self.card_path}/{self.card_path}-DVI-I-*"
        matching_paths = glob.glob(pattern)

        if matching_paths:
            basename = os.path.basename(matching_paths[0])
            connector = basename.split("-", 1)[1]
            print(f"Default connector not found. Using: {connector}")
            return connector

        print(f"No DVI-I connectors found. Falling back to default: {default_connector}")
        return default_connector

    def on_activate(self, app):
        self.win = Adw.ApplicationWindow(application=app)
        self.win.connect("close-request", lambda *_: exit(0))
        self.win.set_default_size(800, 600)
        self.win.set_title("External Displays")

        # Focus change event controllers
        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect("enter", self.on_focus_in)
        focus_controller.connect("leave", self.on_focus_out)
        self.win.add_controller(focus_controller)

        # Keyboard emulator
        self.keyboard_emulator = KeyboardEmulator(self)

        # Toast overlay for notifications
        self.toast_overlay = ui.create_toast_overlay()

        # Toolbar view for the header
        self.toolbar_view = ui.create_toolbar_view()

        # Header bar
        self.header_bar, refresh_button, menu_button = ui.create_header_bar()

        refresh_button.connect("clicked", self.on_refresh_clicked)

        # Menu
        menu_button.set_menu_model(ui.create_menu_model())

        # Hide menu model for now
        menu_button.set_visible(False)

        # Add actions for the menu items
        settings_action = Gio.SimpleAction.new("settings", None)
        settings_action.connect("activate", self.on_settings_action)
        self.add_action(settings_action)

        info_action = Gio.SimpleAction.new("info", None)
        info_action.connect("activate", self.on_info_action)
        self.add_action(info_action)

        # Add header bar to toolbar view
        self.toolbar_view.add_top_bar(self.header_bar)

        # Setup the bottom sheet for settings
        self.bottom_sheet = ui.create_bottom_sheet()

        # Create pages for view stack, input page, configuratin page and view switcher
        self.stack, self.config_page, self.input_page, view_switcher = ui.create_view_stack_pages()
        main_container = ui.create_bottom_sheet_content(self.stack, view_switcher)

        self.bottom_sheet.set_content(main_container)
        self.toolbar_view.set_content(self.bottom_sheet)
        self.toast_overlay.set_child(self.toolbar_view)
        self.win.set_content(self.toast_overlay)

        # Input page status label
        self.status_label = ui.create_status_label()
        self.input_page.append(self.status_label)

        # Sync enable file with services state
        displaylink_active = check_service_status("displaylink-driver.service", system_bus=True)
        externaldisplay_active = check_service_status("externaldisplay.service", system_bus=False)
        self.display_enabled = displaylink_active and externaldisplay_active

        if self.display_enabled and not os.path.exists(self.enable_file_path):
            try:
                open(self.enable_file_path, "a").close()
            except Exception as e:
                print(f"Error creating enable file at startup: {e}")
        elif not self.display_enabled and os.path.exists(self.enable_file_path):
            try:
                os.remove(self.enable_file_path)
            except Exception as e:
                print(f"Error removing enable file at startup: {e}")

        # Build pages
        self.create_main_content()
        self.create_settings_content()
        self.create_config_page()

        self.update_display_ui_state(self.display_enabled)

        if self.display_enabled:
            self.refresh_timeout_id = GLib.timeout_add_seconds(5, self.refresh_display_info)

        # Regain focus periodically (this is a hack)
        GLib.timeout_add(1000, self.regain_focus)

        initial_tab = self.stack.get_visible_child_name()
        if initial_tab == "input":
            self.connect_key_controller()

        self.win.present()

    def get_sysfs_event_name(self, by_id_name, real_path):
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

        hint = None
        if "-if01" in by_id_name:
            hint = "if01"
        elif "-if02" in by_id_name:
            hint = "if02"

        if hint:
            return f"{base_label} ({hint})"
        return base_label

    def load_input_devices(self):
        if not hasattr(self, "inputs_expander") or self.inputs_expander is None:
            return

        # Remove all existing rows that we previously added
        for row in list(self.input_device_rows):
            self.inputs_expander.remove(row)
        self.input_device_rows.clear()

        try:
            settings = Gio.Settings.new("io.furios.input-redirector")
            current_paths = settings.get_string("input-paths")
            selected_paths = set(current_paths.split(",")) if current_paths else set()
        except Exception as e:
            print(f"Error reading input paths from gsettings: {e}")
            selected_paths = set()

        self.input_device_buttons = []

        try:
            devices_path = "/dev/input/by-id"
            if os.path.exists(devices_path):
                devices = sorted(os.listdir(devices_path))

                if not devices:
                    no_devices_row = ui.create_action_row("No input devices found")
                    self.inputs_expander.add_row(no_devices_row)
                    self.input_device_rows.append(no_devices_row)
                else:
                    for device in devices:
                        device_path = os.path.join(devices_path, device)

                        # Only include event devices (skip js devices)
                        if "event" not in device:
                            continue

                        try:
                            real_path = os.path.realpath(device_path)

                            friendly = self.get_sysfs_event_name(device, real_path)

                            device_row = ui.create_action_row(friendly, real_path)

                            checkbox = Gtk.CheckButton()
                            checkbox.set_active(real_path in selected_paths)
                            checkbox.connect("toggled", self.on_input_device_toggled)

                            self.input_device_buttons.append((checkbox, real_path))
                            device_row.add_prefix(checkbox)

                            self.inputs_expander.add_row(device_row)
                            self.input_device_rows.append(device_row)
                        except Exception as e:
                            print(f"Error processing device {device}: {e}")
                            continue
            else:
                no_devices_row = ui.create_action_row("Input devices directory not found")
                self.inputs_expander.add_row(no_devices_row)
                self.input_device_rows.append(no_devices_row)
        except Exception as e:
            print(f"Error listing input devices: {e}")
            error_row = ui.create_action_row("Error loading input devices")
            self.inputs_expander.add_row(error_row)
            self.input_device_rows.append(error_row)

    def update_display_info(self):
        if not self.display_enabled:
            return None

        if not self.display_info_labels:
            return None

        display_info = get_display_info(self.card_path, self.connector)
        for key, value in display_info.items():
            if key in self.display_info_labels:
                self.display_info_labels[key].set_text(value)

        current_resolution = self.get_current_resolution()
        if current_resolution and current_resolution in self.mode_radio_buttons:
            # Only update if the current active button isn't already set to the current resolution
            button = self.mode_radio_buttons[current_resolution]
            if not button.get_active():
                # Temporarily block signal handlers
                if current_resolution in self.mode_radio_handlers:
                    handler_id = self.mode_radio_handlers[current_resolution]
                    button.handler_block(handler_id)
                    button.set_active(True)
                    button.handler_unblock(handler_id)
                else:
                    # If we don't have the handler ID for some reason, just set it active
                    button.set_active(True)

        return display_info

    def on_refresh_clicked(self, _button):
        # Refresh display information
        self.update_display_info()
        self.load_input_devices()
        ui.create_toast(self.toast_overlay, "Refresh complete")

    def connect_key_controller(self):
        if self.key_controller is None:
            self.key_controller = Gtk.EventControllerKey.new()
            self.key_controller.connect("key-pressed", self.keyboard_emulator.on_key_pressed)
            self.key_controller.connect("key-released", self.keyboard_emulator.on_key_released)
            self.win.add_controller(self.key_controller)
            print("Key controller connected")

    def disconnect_key_controller(self):
        if self.key_controller is not None:
            self.win.remove_controller(self.key_controller)
            self.key_controller = None
            print("Key controller disconnected")

    def on_settings_action(self, _action, _parameter):
        self.bottom_sheet.set_open(True)

    def on_info_action(self, _action, _parameter):
        instructions = (
            "• Touch and move to move cursor\n"
            "• Tap for left click\n"
            "• Double tap for double click\n"
            "• Two-finger tap for right click\n"
            "• Touch and hold for drag operations\n"
            "• Two-finger pinch for scroll\n"
        )

        dialog = ui.create_info_dialog(instructions)
        dialog.present(self.win)

    def create_main_content(self):
        # Drawing area for touch events
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_can_focus(True)
        self.drawing_area.set_vexpand(True)
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_draw_func(self.on_draw)

        # Ensure drawing area can receive focus
        self.drawing_area.set_focusable(True)

        # Add key controller to the drawing area
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.keyboard_emulator.on_key_pressed)
        key_controller.connect("key-released", self.keyboard_emulator.on_key_released)
        self.drawing_area.add_controller(key_controller)

        # Frame for the drawing area
        frame = ui.create_drawing_area_frame(self.drawing_area)
        self.input_page.append(frame)

        self.touch_mouse_emulator = TouchMouseEmulator(self.drawing_area, self)

    def get_display_modes(self):
        modes_path = f"/sys/class/drm/{self.card_path}/{self.card_path}-{self.connector}/modes"
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

    def get_current_resolution(self):
        try:
            d = display.Display()
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
                if self.connector in output_name and output_info.crtc:
                    crtc_info = d.xrandr_get_crtc_info(output_info.crtc, resources.config_timestamp)
                    return f"{crtc_info.width}x{crtc_info.height}"

            return None
        except Exception as e:
            print(f"Error getting current resolution with Xlib: {e}")
            return None

    def apply_display_mode(self, mode):
        try:
            subprocess.run(["xrandr", "--output", self.connector, "--mode", mode], check=True)
            ui.create_toast(self.toast_overlay, f"Display mode changed to {mode}")
            return True
        except Exception as e:
            ui.create_toast(self.toast_overlay, f"Failed to change mode: {e}")
            return False

    def on_mode_selected(self, button, mode):
        if button.get_active():
            self.apply_display_mode(mode)

    def create_config_page(self):
        # Add key controller to the config page as well
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.keyboard_emulator.on_key_pressed)
        key_controller.connect("key-released", self.keyboard_emulator.on_key_released)
        self.config_page.add_controller(key_controller)
        self.config_page_key_controller = key_controller

        display_info = get_display_info(self.card_path, self.connector)

        # Scrolled window to make content scrollable
        scrolled = ui.create_scrolled_window()

        # Preferences page
        preferences_page = ui.create_preferences_page()

        management_group = ui.create_preferences_group("Display Management")

        # Display services switch
        services_row = ui.create_action_row(
            "Display Services",
            "Enable/disable display services",
        )

        # Create the switch
        self.display_services_switch = ui.create_switch()

        # Set initial state of switch
        self.display_services_switch.set_active(self.display_enabled)

        # Connect signal
        self.display_services_switch.connect("state-set", self.on_display_services_toggled)

        # Add switch to row
        services_row.add_suffix(self.display_services_switch)
        services_row.set_activatable_widget(self.display_services_switch)

        management_group.add(services_row)
        preferences_page.add(management_group)

        # Display Information group
        info_group = ui.create_preferences_group("Display Information")

        # Status
        status_row = ui.create_action_row("Status", "Current connection status")
        status_row.set_activatable(False)
        self.status_value = ui.create_value_label(display_info.get("status", ""))
        status_row.add_suffix(self.status_value)
        info_group.add(status_row)

        # Power State
        power_row = ui.create_action_row("Power State", "Current power mode")
        power_row.set_activatable(False)
        self.power_value = ui.create_value_label(display_info.get("power_state", ""))
        power_row.add_suffix(self.power_value)
        info_group.add(power_row)

        # Manufacturer
        mfg_row = ui.create_action_row("Manufacturer", "Display manufacturer")
        mfg_row.set_activatable(False)
        self.mfg_value = ui.create_value_label(display_info.get("manufacturer", ""))
        mfg_row.add_suffix(self.mfg_value)
        info_group.add(mfg_row)

        preferences_page.add(info_group)

        self.display_info_labels = {
            "status": self.status_value,
            "power_state": self.power_value,
            "manufacturer": self.mfg_value,
        }

        # Display modes section with expander
        modes_group = ui.create_preferences_group("Display Modes")

        self.modes_expander = ui.create_expander_row(
            "Available Resolutions",
            "Click to select a display mode",
        )

        modes = self.get_display_modes()
        radio_group = None
        current_resolution = None
        if modes:
            current_resolution = self.get_current_resolution()
        else:
            no_modes_row = ui.create_action_row("No display modes available")
            self.modes_expander.add_row(no_modes_row)

        self.mode_radio_buttons.clear()
        self.mode_radio_handlers.clear()

        for mode in modes:
            mode_row = ui.create_action_row(mode)

            radio_button = Gtk.CheckButton()
            if radio_group is None:
                radio_group = radio_button
            else:
                radio_button.set_group(radio_group)

            self.mode_radio_buttons[mode] = radio_button

            if current_resolution and mode == current_resolution:
                radio_button.set_active(True)

            handler_id = radio_button.connect("toggled", self.on_mode_selected, mode)
            self.mode_radio_handlers[mode] = handler_id

            mode_row.add_prefix(radio_button)
            self.modes_expander.add_row(mode_row)

        modes_group.add(self.modes_expander)
        preferences_page.add(modes_group)

        # Hide display modes for now
        modes_group.set_visible(False)

        # Input devices section
        inputs_group = ui.create_preferences_group("Inputs")

        # Expander row for input devices
        self.inputs_expander = ui.create_expander_row("Input Devices", "Select devices to redirect")

        self.load_input_devices()

        inputs_group.add(self.inputs_expander)
        preferences_page.add(inputs_group)

        scrolled.set_child(preferences_page)
        self.config_page.append(scrolled)

    def on_display_services_toggled(self, _switch, state):
        if state:
            self.show_progress_dialog("Starting display services...")
            thread = threading.Thread(target=self.start_display_services, daemon=True)
            thread.start()
        else:
            self.show_progress_dialog("Stopping display services...")
            thread = threading.Thread(target=self.stop_display_services, daemon=True)
            thread.start()
        return False

    def update_display_ui_state(self, enabled):
        if not self.display_info_labels or self.modes_expander is None:
            return

        if enabled:
            if self.refresh_timeout_id is None:
                self.refresh_timeout_id = GLib.timeout_add_seconds(5, self.refresh_display_info)

            self.modes_expander.set_sensitive(True)
            self.inputs_expander.set_sensitive(True)
            self.refresh_display_info()
        else:
            for _key, label in self.display_info_labels.items():
                label.set_text("")

            self.modes_expander.set_sensitive(False)
            self.inputs_expander.set_sensitive(False)

            if self.refresh_timeout_id is not None:
                GLib.source_remove(self.refresh_timeout_id)
                self.refresh_timeout_id = None

    def show_progress_dialog(self, message):
        self.progress_dialog = ui.create_progress_dialog(message)
        self.progress_dialog.present(self.win)

    def ensure_close_progress_dialog(self):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        return False

    def create_settings_content(self):
        content, sens, disp, conn, card, apply_button = ui.create_settings_sheet_content(
            self.target_display,
            self.connector,
            self.card_path,
        )
        self.sensitivity_slider = sens
        self.display_entry = disp
        self.connector_entry = conn
        self.card_entry = card
        self.apply_button = apply_button

        self.apply_button.connect("clicked", self.on_apply_settings)
        self.bottom_sheet.set_sheet(content)

    def on_apply_settings(self, _button):
        # Sensitivity
        try:
            self.touch_mouse_emulator.sensitivity = float(self.sensitivity_slider.get_value())
        except Exception as e:
            print(f"Failed to update sensitivity: {e}")

        # Display
        entry_text = self.display_entry.get_text()
        if entry_text and entry_text != self.target_display:
            self.target_display = entry_text
            os.environ["DISPLAY"] = self.target_display
            self.set_input_redirector_display()
            self.touch_mouse_emulator.update_target_dimensions()

        # Connector / card path
        connector_updated = False
        card_updated = False

        new_connector = self.connector_entry.get_text()
        new_card = self.card_entry.get_text()

        if new_connector and new_connector != self.connector:
            self.connector = new_connector
            connector_updated = True

        if new_card and new_card != self.card_path:
            self.card_path = new_card
            card_updated = True

        if connector_updated or card_updated:
            # Clear config page and rebuild
            for child in list(self.config_page.get_children()):
                self.config_page.remove(child)
            self.create_config_page()
            self.refresh_display_info()

        self.bottom_sheet.set_open(False)

    def on_input_device_toggled(self, _button):
        paths = [real for btn, real in self.input_device_buttons if btn.get_active()]
        val = ",".join(paths)
        settings = Gio.Settings.new("io.furios.input-redirector")
        settings.set_string("input-paths", val)

    def set_input_redirector_display(self):
        schema = "io.furios.input-redirector"
        key = "display"
        try:
            source = Gio.SettingsSchemaSource.get_default()
            if not source or not source.lookup(schema, False):
                return
            settings = Gio.Settings.new(schema)
            settings.set_string(key, self.target_display)
        except Exception as e:
            print(f"Failed to set input redirector display: {e}")

    def start_display_services(self):
        try:
            success = True

            self.set_input_redirector_display()

            try:
                open(self.enable_file_path, "a").close()
            except Exception as e:
                print(f"Error creating enable file: {e}")
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Failed to enable display services")
                success = False

            if not start_service("displaylink-driver.service", system_bus=True):
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Failed to start displaylink driver")
                success = False

            if success and not wait_for_file("/sys/class/drm/card1"):
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Timeout waiting for display")
                success = False

            if success and not wait_for_display_connected(self.card_path, self.connector):
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Timeout waiting for display connection")
                success = False

            if success and not start_service("external-display-display-server.service", system_bus=True):
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Failed to start display server")
                success = False

            if success and not start_service("externaldisplay.service"):
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Failed to start external display service")
                success = False

            if not start_service("input-redirector.service"):
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Failed to start input redirector")
                success = False

            self.set_gnome_wm_preference(":minimize,maximize,close")

            if success:
                GLib.idle_add(ui.create_toast, self.toast_overlay, "Display services enabled successfully")
                GLib.idle_add(self.update_display_ui_state, True)
                self.display_enabled = True
            else:
                # Restore if we failed
                self.set_gnome_wm_preference("appmenu:")

                if os.path.exists(self.enable_file_path):
                    try:
                        os.remove(self.enable_file_path)
                    except Exception as e:
                        print(f"Error removing enable file after failure: {e}")
                GLib.idle_add(lambda: self.display_services_switch.set_active(False))
                self.display_enabled = False

            GLib.idle_add(self.ensure_close_progress_dialog, priority=GLib.PRIORITY_HIGH)
        except Exception as e:
            print(f"Unexpected error in start_display_services: {e}")
            GLib.idle_add(ui.create_toast, self.toast_overlay, f"Error enabling display services: {e}")
            GLib.idle_add(lambda: self.display_services_switch.set_active(False))
            self.display_enabled = False

            self.set_gnome_wm_preference("appmenu:")

            GLib.idle_add(self.ensure_close_progress_dialog, priority=GLib.PRIORITY_HIGH)

        return False

    def stop_display_services(self):
        try:
            # Restore original layout
            self.set_gnome_wm_preference("appmenu:")

            if os.path.exists(self.enable_file_path):
                try:
                    os.remove(self.enable_file_path)
                except Exception as e:
                    print(f"Error removing enable file: {e}")
                    GLib.idle_add(ui.create_toast, self.toast_overlay, "Failed to disable display services")

            stop_service("externaldisplay.service")
            stop_service("input-redirector.service")
            stop_service("external-display-display-server.service", system_bus=True)

            try:
                settings = Gio.Settings.new("io.furios.input-redirector")
                settings.set_string("input-paths", "")
                print("Cleared input-redirector input-paths")
            except Exception as e:
                print(f"Error clearing input paths: {e}")

            GLib.idle_add(ui.create_toast, self.toast_overlay, "Display services stopped successfully")
            GLib.idle_add(self.update_display_ui_state, False)
            GLib.idle_add(self.ensure_close_progress_dialog, priority=GLib.PRIORITY_HIGH)
            self.display_enabled = False
        except Exception as e:
            print(f"Unexpected error in stop_display_services: {e}")
            GLib.idle_add(ui.create_toast, self.toast_overlay, f"Error stopping display services: {e}")
            GLib.idle_add(self.ensure_close_progress_dialog, priority=GLib.PRIORITY_HIGH)
            self.display_enabled = False

        return False

    def refresh_display_info(self):
        display_info = self.update_display_info()
        if not display_info:
            return True

        if display_info.get("status") == "connected":
            if self.refresh_timeout_id:
                GLib.source_remove(self.refresh_timeout_id)
        return True

    def on_draw(self, area, cr, width, height):
        return self.touch_mouse_emulator.on_draw(area, cr, width, height)

    def on_focus_in(self, _controller):
        print("Window received focus")
        self.start_focus_regain()

    def on_focus_out(self, _controller):
        print("Window lost focus")
        self.stop_focus_regain()

    def start_focus_regain(self):
        if not self.focus_regain_active:
            self.focus_regain_active = True
            self.focus_regain_source_id = GLib.timeout_add(1000, self.regain_focus)
            print("Focus regain started")

    def stop_focus_regain(self):
        if self.focus_regain_active and self.focus_regain_source_id is not None:
            GLib.source_remove(self.focus_regain_source_id)
            self.focus_regain_source_id = None
            self.focus_regain_active = False
            print("Focus regain stopped")

    def regain_focus(self):
        if self.focus_regain_active:
            self.win.present()

            # If we're on the input tab, ensure drawing area has focus
            if self.stack.get_visible_child_name() == "input":
                self.drawing_area.grab_focus()
            return GLib.SOURCE_CONTINUE
        return GLib.SOURCE_REMOVE
