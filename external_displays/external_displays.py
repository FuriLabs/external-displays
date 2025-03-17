# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2025 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import gi
import os
import time
import threading
import subprocess
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GLib, Adw, Gio
from Xlib import display
from external_displays.edid import get_display_info
from external_displays.keyboard_emulator import KeyboardEmulator
from external_displays.touch_mouse_emulator import TouchMouseEmulator
from external_displays.utils import check_service_status, start_service, stop_service, wait_for_file, wait_for_display_connected

class ExternalDisplays(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect('activate', self.on_activate)

        self.target_display = os.environ.get('DISPLAY', ':1')
        self.card_path = "card1"
        self.connector = "DVI-I-1"

        self.mode_radio_buttons = {}
        self.mode_radio_handlers = {}

        # Flag to track if focus regain is active
        self.focus_regain_active = False
        self.focus_regain_source_id = None

        self.enable_file_path = os.path.expanduser("~/.enable_external_display")

    def on_activate(self, app):
        self.win = Adw.ApplicationWindow(application=app)
        self.win.connect("close-request", lambda _: exit(0))
        self.win.set_default_size(800, 600)
        self.win.set_title("External Displays")

        # Focus change event controllers
        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect("enter", self.on_focus_in)
        focus_controller.connect("leave", self.on_focus_out)
        self.win.add_controller(focus_controller)

        # Keyboard emulator
        self.keyboard_emulator = KeyboardEmulator(self)

        # Make the window capture keyboard events
        self.win.set_can_focus(True)
        self.key_controller = None

        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()

        # Toolbar view for the header
        self.toolbar_view = Adw.ToolbarView()

        # Header bar
        self.header_bar = Adw.HeaderBar()

        # Menu
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")

        # Menu model
        menu = Gio.Menu.new()
        menu.append("Settings", "app.settings")
        menu.append("Info", "app.info")

        menu_button.set_menu_model(menu)
        self.header_bar.pack_end(menu_button)

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
        self.bottom_sheet = Adw.BottomSheet()
        self.bottom_sheet.set_can_open(True)
        self.bottom_sheet.set_modal(True)

        # Create pages for view stack
        self.stack = Adw.ViewStack()

        # Configuration page
        clamp = Adw.Clamp()
        self.config_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        clamp.set_child(self.config_page)

        self.stack.add_titled_with_icon(clamp, "config", "Configuration", "emblem-system-symbolic")

        # Create the Input page
        input_clamp = Adw.Clamp()
        self.input_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.input_page.set_margin_top(10)
        self.input_page.set_margin_bottom(10)
        self.input_page.set_margin_start(10)
        self.input_page.set_margin_end(10)
        input_clamp.set_child(self.input_page)

        self.stack.add_titled_with_icon(input_clamp, "input", "Input", "input-keyboard-symbolic")

        # View switcher for bottom
        view_switcher = Adw.ViewSwitcherBar()
        view_switcher.set_stack(self.stack)
        view_switcher.set_reveal(True)

        main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_container.append(self.stack)
        main_container.append(view_switcher)

        self.bottom_sheet.set_content(main_container)
        self.toolbar_view.set_content(self.bottom_sheet)
        self.toast_overlay.set_child(self.toolbar_view)
        self.win.set_content(self.toast_overlay)

        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        self.status_label.set_margin_top(5)
        self.input_page.append(self.status_label)

        self.create_main_content()
        self.create_settings_content()

        self.create_config_page()

        displaylink_active = check_service_status("displaylink-driver.service", system_bus=True)
        display_server_active = check_service_status("external-display-display-server.service", system_bus=True)
        services_enabled = displaylink_active and display_server_active

        if services_enabled and not os.path.exists(self.enable_file_path):
            try:
                open(self.enable_file_path, 'a').close()
            except Exception as e:
                print(f"Error creating enable file at startup: {e}")
        elif not services_enabled and os.path.exists(self.enable_file_path):
            try:
                os.remove(self.enable_file_path)
            except Exception as e:
                print(f"Error removing enable file at startup: {e}")

        self.update_display_ui_state(services_enabled)

        self.refresh_timeout_id = None
        if services_enabled:
            self.refresh_timeout_id = GLib.timeout_add_seconds(5, self.refresh_display_info)

        # Regain focus periodically (this is a hack)
        GLib.timeout_add(1000, self.regain_focus)

        initial_tab = self.stack.get_visible_child_name()
        if initial_tab == "input":
            self.connect_key_controller()

        self.win.present()

    def connect_key_controller(self):
        if not hasattr(self, 'key_controller') or self.key_controller is None:
            self.key_controller = Gtk.EventControllerKey.new()
            self.key_controller.connect("key-pressed", self.keyboard_emulator.on_key_pressed)
            self.key_controller.connect("key-released", self.keyboard_emulator.on_key_released)
            self.win.add_controller(self.key_controller)
            print("Key controller connected")

    def disconnect_key_controller(self):
        if hasattr(self, 'key_controller') and self.key_controller is not None:
            self.win.remove_controller(self.key_controller)
            self.key_controller = None
            print("Key controller disconnected")

    def on_settings_action(self, action, parameter):
        self.bottom_sheet.set_open(True)

    def on_info_action(self, action, parameter):
        instructions = (
            "• Touch and move to move cursor\n"
            "• Tap for left click\n"
            "• Double tap for double click\n"
            "• Two-finger tap for right click\n"
            "• Touch and hold for drag operations\n"
            "• Two-finger pinch for scroll\n"
        )

        dialog = Adw.Dialog.new()
        dialog.set_content_width(400)
        dialog.set_content_height(300)
        dialog.set_title("Usage Instructions")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        # Header bar for the dialog
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(True)
        content.append(header)

        # Instructions label
        label = Gtk.Label()
        label.set_markup(instructions)
        label.set_wrap(True)
        label.set_xalign(0)
        label.set_vexpand(True)
        content.append(label)

        # Set the dialog child
        dialog.set_child(content)

        # Present the dialog
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
        frame = Gtk.Frame()
        frame.set_child(self.drawing_area)
        self.input_page.append(frame)

        self.touch_mouse_emulator = TouchMouseEmulator(
            self.drawing_area, self
        )

    def get_display_modes(self):
        modes_path = f"/sys/class/drm/{self.card_path}/{self.card_path}-{self.connector}/modes"
        if os.path.exists(modes_path):
            try:
                with open(modes_path, 'r') as f:
                    modes = [line.strip() for line in f.readlines()]
                # Deduplicate the list while preserving order
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

            if not hasattr(d, 'randr_version'):
                width = screen.width_in_pixels
                height = screen.height_in_pixels
                return f"{width}x{height}"

            resources = root.xrandr_get_screen_resources()

            for output in resources.outputs:
                output_info = d.xrandr_get_output_info(output, resources.config_timestamp)

                if output_info.connection != 0:  # 0 is Connected
                    continue

                output_name = output_info.name
                if self.connector in output_name:
                    if output_info.crtc:
                        crtc_info = d.xrandr_get_crtc_info(output_info.crtc, resources.config_timestamp)
                        width = crtc_info.width
                        height = crtc_info.height
                        return f"{width}x{height}"
            return None
        except Exception as e:
            print(f"Error getting current resolution with Xlib: {e}")
            return None

    def apply_display_mode(self, mode):
        try:
            cmd = ["xrandr", "--output", self.connector, "--mode", mode]
            subprocess.run(cmd, check=True)
            self.show_toast(f"Display mode changed to {mode}")
            return True
        except Exception as e:
            self.show_toast(f"Failed to change mode: {e}")
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

        # Store the controller reference
        self.config_page_key_controller = key_controller

        display_info = get_display_info(self.card_path, self.connector)

        # Scrolled window to make content scrollable
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)

        # Preferences page
        preferences_page = Adw.PreferencesPage()

        management_group = Adw.PreferencesGroup()
        management_group.set_title("Display Management")

        # Display services switch
        services_row = Adw.ActionRow()
        services_row.set_title("Display Services")
        services_row.set_subtitle("Enable/disable display services")

        # Create the switch
        self.display_services_switch = Gtk.Switch()
        self.display_services_switch.set_valign(Gtk.Align.CENTER)

        # Check initial state of services
        displaylink_active = check_service_status("displaylink-driver.service", system_bus=True)
        display_server_active = check_service_status("external-display-display-server.service", system_bus=True)

        # Set initial state of switch
        self.display_services_switch.set_active(displaylink_active and display_server_active)

        # Connect signal
        self.display_services_switch.connect("state-set", self.on_display_services_toggled)

        # Add switch to row
        services_row.add_suffix(self.display_services_switch)
        services_row.set_activatable_widget(self.display_services_switch)

        management_group.add(services_row)
        preferences_page.add(management_group)

        # Display Information group
        info_group = Adw.PreferencesGroup()
        info_group.set_title("Display Information")

        # Status
        status_row = Adw.ActionRow()
        status_row.set_title("Status")
        status_row.set_subtitle("Current connection status")
        status_row.set_activatable(False)
        self.status_value = Gtk.Label(label=display_info['status'])
        self.status_value.set_valign(Gtk.Align.CENTER)
        self.status_value.set_ellipsize(True)
        self.status_value.set_selectable(True)
        status_row.add_suffix(self.status_value)
        info_group.add(status_row)

        # Power State
        power_row = Adw.ActionRow()
        power_row.set_title("Power State")
        power_row.set_subtitle("Current power mode")
        power_row.set_activatable(False)
        self.power_value = Gtk.Label(label=display_info['power_state'])
        self.power_value.set_valign(Gtk.Align.CENTER)
        self.power_value.set_ellipsize(True)
        self.power_value.set_selectable(True)
        power_row.add_suffix(self.power_value)
        info_group.add(power_row)

        # Manufacturer
        mfg_row = Adw.ActionRow()
        mfg_row.set_title("Manufacturer")
        mfg_row.set_subtitle("Display manufacturer")
        mfg_row.set_activatable(False)
        self.mfg_value = Gtk.Label(label=display_info['manufacturer'])
        self.mfg_value.set_valign(Gtk.Align.CENTER)
        self.mfg_value.set_ellipsize(True)
        self.mfg_value.set_selectable(True)
        mfg_row.add_suffix(self.mfg_value)
        info_group.add(mfg_row)

        preferences_page.add(info_group)

        self.display_info_labels = {
            'status': self.status_value,
            'power_state': self.power_value,
            'manufacturer': self.mfg_value
        }

        # Display modes section with Adwaita expander
        modes_group = Adw.PreferencesGroup()
        modes_group.set_title("Display Modes")

        # Expander row
        self.modes_expander = Adw.ExpanderRow()
        self.modes_expander.set_title("Available Resolutions")
        self.modes_expander.set_subtitle("Click to select a display mode")

        # Get display modes
        modes = self.get_display_modes()

        # Radio button group
        radio_group = None

        # No modes available message
        if not modes:
            no_modes_row = Adw.ActionRow()
            no_modes_row.set_title("No display modes available")
            self.modes_expander.add_row(no_modes_row)
        else:
            # Get current resolution
            current_resolution = self.get_current_resolution()

        self.mode_radio_buttons.clear()
        self.mode_radio_handlers.clear()

        for mode in modes:
            mode_row = Adw.ActionRow()
            mode_row.set_title(mode)

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

        scrolled_window.set_child(preferences_page)

        self.config_page.append(scrolled_window)

    def on_display_services_toggled(self, switch, state):
        if state:
            self.show_progress_dialog("Starting display services...")
            thread = threading.Thread(target=self.start_display_services)
            thread.daemon = True
            thread.start()
        else:
            self.show_progress_dialog("Stopping display services...")
            thread = threading.Thread(target=self.stop_display_services)
            thread.daemon = True
            thread.start()
        return False

    def update_display_ui_state(self, enabled):
        if not hasattr(self, 'display_info_labels') or not hasattr(self, 'modes_expander'):
            return

        if enabled:
            if not hasattr(self, 'refresh_timeout_id') or self.refresh_timeout_id is None:
                self.refresh_timeout_id = GLib.timeout_add_seconds(5, self.refresh_display_info)

            self.modes_expander.set_sensitive(True)

            self.refresh_display_info()
        else:
            for key, label in self.display_info_labels.items():
                label.set_text("")

            self.modes_expander.set_sensitive(False)

            if hasattr(self, 'refresh_timeout_id') and self.refresh_timeout_id is not None:
                GLib.source_remove(self.refresh_timeout_id)
                self.refresh_timeout_id = None

    def show_progress_dialog(self, message):
        self.progress_dialog = Adw.Dialog.new()
        self.progress_dialog.set_content_width(350)
        self.progress_dialog.set_content_height(150)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)
        spinner.start()
        content.append(spinner)

        label = Gtk.Label(label=message)
        content.append(label)

        self.progress_dialog.set_child(content)
        self.progress_dialog.present(self.win)

    def ensure_close_progress_dialog(self):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        return False

    def start_display_services(self):
        try:
            success = True

            try:
                open(self.enable_file_path, 'a').close()
            except Exception as e:
                print(f"Error creating enable file: {e}")
                GLib.idle_add(self.show_toast, "Failed to enable display services")
                success = False

            if not start_service("displaylink-driver.service", system_bus=True):
                GLib.idle_add(self.show_toast, "Failed to start displaylink driver")
                success = False

            if success:
                if not wait_for_file("/sys/class/drm/card0"):
                    GLib.idle_add(self.show_toast, "Timeout waiting for display")
                    success = False

            if success:
                if not wait_for_display_connected(self.card_path, self.connector):
                    GLib.idle_add(self.show_toast, "Timeout waiting for display connection")
                    success = False

            if success:
                if not start_service("external-display-display-server.service", system_bus=True):
                    GLib.idle_add(self.show_toast, "Failed to start display server")
                    success = False

            if success:
                if not start_service("externaldisplay.service"):
                    GLib.idle_add(self.show_toast, "Failed to start external display service")
                    success = False

            if success:
                GLib.idle_add(self.show_toast, "Display services enabled successfully")
                GLib.idle_add(self.update_display_ui_state, True)
            else:
                if os.path.exists(self.enable_file_path):
                    try:
                        os.remove(self.enable_file_path)
                    except Exception as e:
                        print(f"Error removing enable file after failure: {e}")

                GLib.idle_add(lambda: self.display_services_switch.set_active(False))

            GLib.idle_add(self.ensure_close_progress_dialog, priority=GLib.PRIORITY_HIGH)
        except Exception as e:
            print(f"Unexpected error in start_display_services: {e}")
            GLib.idle_add(self.show_toast, f"Error enabling display services: {e}")
            GLib.idle_add(lambda: self.display_services_switch.set_active(False))
            GLib.idle_add(self.close_progress_dialog)

        return False

    def stop_display_services(self):
        try:
            if os.path.exists(self.enable_file_path):
                try:
                    os.remove(self.enable_file_path)
                except Exception as e:
                    print(f"Error removing enable file: {e}")
                    GLib.idle_add(self.show_toast, f"Failed to disable display services")

            stop_service("externaldisplay.service")
            stop_service("external-display-display-server.service", system_bus=True)
            stop_service("displaylink-driver.service", system_bus=True)

            GLib.idle_add(self.show_toast, "Display services stopped successfully")
            GLib.idle_add(self.update_display_ui_state, False)
            GLib.idle_add(self.ensure_close_progress_dialog, priority=GLib.PRIORITY_HIGH)
        except Exception as e:
            print(f"Unexpected error in stop_display_services: {e}")
            GLib.idle_add(self.show_toast, f"Error stopping display services: {e}")
            GLib.idle_add(self.ensure_close_progress_dialog, priority=GLib.PRIORITY_HIGH)

        return False

    def refresh_display_info(self):
        if not hasattr(self, 'display_info_labels'):
            return True

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

        return True

    def create_settings_content(self):
        self.bottom_sheet.set_can_open(True)
        self.bottom_sheet.set_modal(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        # Sensitivity adjustment
        sensitivity_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sensitivity_label = Gtk.Label(label="Motion Sensitivity", halign=Gtk.Align.START)
        sensitivity_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        sensitivity_slider.set_range(0.5, 3.0)
        sensitivity_slider.set_draw_value(True)
        sensitivity_slider.set_value(2.0)
        sensitivity_slider.set_hexpand(True)
        sensitivity_box.append(sensitivity_label)
        sensitivity_box.append(sensitivity_slider)
        content.append(sensitivity_box)

        # Display selector
        display_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        display_label = Gtk.Label(label="Target Display")
        display_input = Gtk.Entry()
        display_input.set_text(self.target_display)
        display_input.set_hexpand(True)
        display_box.append(display_label)
        display_box.append(display_input)
        content.append(display_box)

        # Connector settings
        connector_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        connector_label = Gtk.Label(label="Connector")
        connector_input = Gtk.Entry()
        connector_input.set_text(self.connector)
        connector_input.set_hexpand(True)
        connector_box.append(connector_label)
        connector_box.append(connector_input)
        content.append(connector_box)

        # Card path settings
        card_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card_label = Gtk.Label(label="Card Path")
        card_input = Gtk.Entry()
        card_input.set_text(self.card_path)
        card_input.set_hexpand(True)
        card_box.append(card_label)
        card_box.append(card_input)
        content.append(card_box)

        # Apply button
        apply_button = Gtk.Button(label="Apply Settings")
        apply_button.connect("clicked", self.on_apply_settings)
        content.append(apply_button)

        self.bottom_sheet.set_sheet(content)

    def on_apply_settings(self, button):
        sheet = self.bottom_sheet.get_sheet()
        sensitivity_updated = False
        display_updated = False
        connector_updated = False
        card_updated = False

        for child in sheet:
            if isinstance(child, Gtk.Box):
                for box_child in child:
                    if isinstance(box_child, Gtk.Scale) and not sensitivity_updated:
                        sensitivity = box_child.get_value()
                        self.touch_mouse_emulator.sensitivity = sensitivity
                        self.show_toast(f"Sensitivity set to {sensitivity}")
                        sensitivity_updated = True
                    elif isinstance(box_child, Gtk.Entry):
                        entry_text = box_child.get_text()
                        if not display_updated and child.get_first_child().get_text() == "Target Display":
                            if entry_text != self.target_display:
                                self.target_display = entry_text
                                os.environ['DISPLAY'] = self.target_display
                                self.touch_mouse_emulator.update_target_dimensions()
                                self.show_toast(f"Target display changed to {self.target_display}")
                                display_updated = True
                        elif not connector_updated and child.get_first_child().get_text() == "Connector":
                            if entry_text != self.connector:
                                self.connector = entry_text
                                self.show_toast(f"Connector changed to {self.connector}")
                                connector_updated = True
                        elif not card_updated and child.get_first_child().get_text() == "Card Path":
                            if entry_text != self.card_path:
                                self.card_path = entry_text
                                self.show_toast(f"Card path changed to {self.card_path}")
                                card_updated = True

        if connector_updated or card_updated:
            for child in self.config_page.get_children():
                self.config_page.remove(child)
            self.create_config_page()
            self.refresh_display_info()

        self.bottom_sheet.set_open(False)

    def on_draw(self, area, cr, width, height):
        return self.touch_mouse_emulator.on_draw(area, cr, width, height)

    def show_toast(self, message):
        toast = Adw.Toast.new(message)
        self.toast_overlay.add_toast(toast)

    def on_focus_in(self, controller):
        print("Window received focus")
        self.start_focus_regain()

    def on_focus_out(self, controller):
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
