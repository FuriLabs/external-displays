# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2025 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import gi
from gi.repository import Gdk
import subprocess

class KeyboardEmulator:
    def __init__(self, app):
        self.app = app

        self.active_modifiers = {
            'ctrl': False,
            'alt': False,
            'shift': False,
            'super': False
        }

    def on_key_pressed(self, controller, keyval, keycode, state):
        """Handle key presses and forward them to xdotool"""
        try:
            # Get the key name or character
            keyname = Gdk.keyval_name(keyval)

            if keyname in ['Return', 'BackSpace', 'Tab', 'space', 'Up', 'Down', 'Left', 'Right',
                           'Home', 'End', 'Page_Up', 'Page_Down', 'Delete', 'Insert']:
                self.execute_command(f"xdotool key {keyname}")
            elif keyname in ['Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Shift_L', 'Shift_R', 'Super_L', 'Super_R']:
                # Map the modifier keys to their base name
                modifier_map = {
                    'Control_L': 'ctrl', 'Control_R': 'ctrl',
                    'Alt_L': 'alt', 'Alt_R': 'alt',
                    'Shift_L': 'shift', 'Shift_R': 'shift',
                    'Super_L': 'super', 'Super_R': 'super'
                }

                # Send keydown if not already pressed
                if not self.active_modifiers[modifier_map[keyname]]:
                    self.active_modifiers[modifier_map[keyname]] = True
                    self.execute_command(f"xdotool keydown {modifier_map[keyname]}")
            # Handle function keys
            elif keyname.startswith('F') and keyname[1:].isdigit():
                self.execute_command(f"xdotool key {keyname}")
            # Handle regular characters by typing them
            else:
                # Convert keyval to character
                char = chr(keyval)
                if char.isprintable():
                    # Special handling for ctrl/alt combinations
                    modifiers = Gdk.ModifierType(state)
                    if (modifiers & Gdk.ModifierType.CONTROL_MASK) and (modifiers & Gdk.ModifierType.ALT_MASK):
                        # Ctrl+Alt combo
                        self.execute_command(f"xdotool key ctrl+alt+{char.lower()}")
                    elif modifiers & Gdk.ModifierType.CONTROL_MASK:
                        # Ctrl combo
                        self.execute_command(f"xdotool key ctrl+{char.lower()}")
                    elif modifiers & Gdk.ModifierType.ALT_MASK:  # ALT_MASK for Alt
                        # Alt combo
                        self.execute_command(f"xdotool key alt+{char.lower()}")
                    else:
                        # Regular character
                        self.execute_command(f"xdotool type '{char}'")
                else:
                    print(f"Unhandled key: {keyname}")
        except Exception as e:
            print(f"Error sending key: {str(e)}")
        return True

    def on_key_released(self, controller, keyval, keycode, state):
        """Handle key release events for modifier keys"""
        try:
            keyname = Gdk.keyval_name(keyval)

            # Handle modifier key releases
            if keyname in ['Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Shift_L', 'Shift_R', 'Super_L', 'Super_R']:
                modifier_map = {
                    'Control_L': 'ctrl', 'Control_R': 'ctrl',
                    'Alt_L': 'alt', 'Alt_R': 'alt',
                    'Shift_L': 'shift', 'Shift_R': 'shift',
                    'Super_L': 'super', 'Super_R': 'super'
                }

                # Release the modifier key
                self.active_modifiers[modifier_map[keyname]] = False
                self.execute_command(f"xdotool keyup {modifier_map[keyname]}")
        except Exception as e:
            print(f"Error on key release: {str(e)}")

        return False

    def execute_command(self, command):
        """Execute an xdotool command"""
        try:
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Command error: {str(e)}")
