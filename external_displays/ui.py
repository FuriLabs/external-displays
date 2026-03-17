# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio

def create_toast_overlay() -> Adw.ToastOverlay:
    return Adw.ToastOverlay()

def create_toolbar_view() -> Adw.ToolbarView:
    return Adw.ToolbarView()

def create_header_bar() -> tuple[Adw.HeaderBar, Gtk.Button, Gtk.MenuButton]:
    header_bar = Adw.HeaderBar()

    refresh_button = Gtk.Button()
    refresh_button.set_icon_name("view-refresh-symbolic")
    refresh_button.set_tooltip_text("Refresh display information and input devices")
    header_bar.pack_start(refresh_button)

    menu_button = Gtk.MenuButton()
    menu_button.set_icon_name("open-menu-symbolic")
    header_bar.pack_end(menu_button)

    return header_bar, refresh_button, menu_button

def create_menu_model() -> Gio.Menu:
    menu = Gio.Menu.new()
    menu.append("Settings", "app.settings")
    menu.append("Info", "app.info")
    return menu

def create_bottom_sheet() -> Adw.BottomSheet:
    sheet = Adw.BottomSheet()
    sheet.set_can_open(True)
    sheet.set_modal(True)
    return sheet

def create_view_stack_pages() -> tuple[Adw.ViewStack, Gtk.Box, Gtk.Box, Adw.ViewSwitcherBar]:
    stack = Adw.ViewStack()

    # Config page
    config_clamp = Adw.Clamp()
    config_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    config_clamp.set_child(config_page)
    stack.add_titled_with_icon(config_clamp, "config", "Configuration", "emblem-system-symbolic")

    # Input page
    input_clamp = Adw.Clamp()
    input_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    input_page.set_margin_top(10)
    input_page.set_margin_bottom(10)
    input_page.set_margin_start(10)
    input_page.set_margin_end(10)
    input_clamp.set_child(input_page)
    stack.add_titled_with_icon(input_clamp, "input", "Input", "input-keyboard-symbolic")

    # View switcher for bottom
    view_switcher = Adw.ViewSwitcherBar()
    view_switcher.set_stack(stack)
    view_switcher.set_reveal(True)

    return stack, config_page, input_page, view_switcher

def create_bottom_sheet_content(stack: Adw.ViewStack, view_switcher: Adw.ViewSwitcherBar) -> Gtk.Box:
    main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    main_container.append(stack)
    main_container.append(view_switcher)
    return main_container

def create_status_label() -> Gtk.Label:
    label = Gtk.Label()
    label.set_xalign(0)
    label.set_margin_top(5)
    return label

def create_drawing_area_frame(drawing_area: Gtk.DrawingArea) -> Gtk.Frame:
    frame = Gtk.Frame()
    frame.set_child(drawing_area)
    return frame

def create_scrolled_window() -> Gtk.ScrolledWindow:
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_vexpand(True)
    return scrolled

def create_preferences_page() -> Adw.PreferencesPage:
    return Adw.PreferencesPage()

def create_preferences_group(title: str) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup()
    group.set_title(title)
    return group

def create_action_row(title: str, subtitle: str | None = None) -> Adw.ActionRow:
    row = Adw.ActionRow()
    row.set_title(title)
    if subtitle is not None:
        row.set_subtitle(subtitle)
    return row

def create_value_label(text: str = "") -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_valign(Gtk.Align.CENTER)
    label.set_ellipsize(True)
    label.set_selectable(True)
    return label

def create_switch() -> Gtk.Switch:
    switch = Gtk.Switch()
    switch.set_valign(Gtk.Align.CENTER)
    return switch

def create_expander_row(title: str, subtitle: str | None = None) -> Adw.ExpanderRow:
    expander = Adw.ExpanderRow()
    expander.set_title(title)
    if subtitle is not None:
        expander.set_subtitle(subtitle)
    return expander

def create_banner(title: str) -> Adw.Banner:
    banner = Adw.Banner()
    banner.set_title(title)
    banner.set_revealed(False)
    banner.set_button_label("")
    banner.set_margin_top(0)
    banner.set_margin_bottom(0)
    banner.set_margin_start(0)
    banner.set_margin_end(0)
    return banner

def create_progress_dialog(message: str) -> Adw.Dialog:
    dialog = Adw.Dialog.new()
    dialog.set_content_width(350)
    dialog.set_content_height(150)

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

    dialog.set_child(content)
    return dialog

def create_info_dialog(instructions: str) -> Adw.Dialog:
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
    return dialog

def create_settings_sheet_content() -> tuple[Gtk.Box, Gtk.Scale, Gtk.Button]:
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

    # Apply button
    apply_button = Gtk.Button(label="Apply Settings")
    content.append(apply_button)

    return content, sensitivity_slider, apply_button

def create_toast(toast_overlay: Adw.ToastOverlay, message: str) -> None:
    print(message)
    toast_overlay.add_toast(Adw.Toast.new(message))
