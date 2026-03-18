# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import os
import gi
from gi.repository import Gdk

from xkbcommon import xkb

from external_displays.input_redirector import InputRedirector

# evdev modifier codes
KEY_LEFTSHIFT = 42
KEY_RIGHTALT = 100

class KeyboardEmulator:
    def __init__(self, app):
        self.app = app
        self.input_redirector = InputRedirector(source="app:external-displays")

        # Track active synthesized combos
        self.active = {}

        self.special_evdev = {
            "Escape": 1,
            "Tab": 15,
            "Return": 28,
            "BackSpace": 14,
            "Delete": 111,
            "Insert": 110,
            "Home": 102,
            "End": 107,
            "Page_Up": 104,
            "Page_Down": 109,
            "Up": 103,
            "Down": 108,
            "Left": 105,
            "Right": 106,
            "Caps_Lock": 58,
            "space": 57,
        }

        self.modifier_evdev = {
            "Shift_L": 42,
            "Shift_R": 54,
            "Control_L": 29,
            "Control_R": 97,
            "Alt_L": 56,
            "Alt_R": 100,
            "Super_L": 125,
            "Super_R": 126,
            "Menu": 127,
        }

        self.named_keys = {
            "shift": "Shift_L",
            "shift_l": "Shift_L",
            "shift_r": "Shift_R",
            "ctrl": "Control_L",
            "control": "Control_L",
            "ctrl_l": "Control_L",
            "control_l": "Control_L",
            "ctrl_r": "Control_R",
            "control_r": "Control_R",
            "alt": "Alt_L",
            "alt_l": "Alt_L",
            "alt_r": "Alt_R",
            "super": "Super_L",
            "meta": "Super_L",
            "win": "Super_L",
            "super_l": "Super_L",
            "super_r": "Super_R",
            "esc": "Escape",
            "escape": "Escape",
            "tab": "Tab",
            "caps": "Caps_Lock",
            "caps_lock": "Caps_Lock",
            "caps lock": "Caps_Lock",
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
        }

        # Track active direct modifier presses
        self.direct_active_modifiers = set()

        self.xkb_ctx = xkb.Context()
        self.xkb_keymap = self.compile_keymap()
        self.xkb_min = int(self.xkb_keymap.min_keycode())
        self.xkb_max = int(self.xkb_keymap.max_keycode())
        self.xkb_layouts = int(self.xkb_keymap.num_layouts())

        # keysym(int) -> (evdev_key(int), [mods...])
        self.keysym_to_combo = {}
        self.build_reverse_map()

    def compile_keymap(self):
        rules = os.environ.get("XKB_DEFAULT_RULES")
        model = os.environ.get("XKB_DEFAULT_MODEL")
        layout = os.environ.get("XKB_DEFAULT_LAYOUT")
        variant = os.environ.get("XKB_DEFAULT_VARIANT")
        options = os.environ.get("XKB_DEFAULT_OPTIONS")

        try:
            return self.xkb_ctx.keymap_new_from_names(
                rules=rules,
                model=model,
                layout=layout,
                variant=variant,
                options=options,
            )
        except Exception as e:
            print(f"KeyboardEmulator: failed to compile XKB keymap from env: {e}")
            return self.xkb_ctx.keymap_new_from_names()

    def press(self, evdev: int):
        self.input_redirector.key_event_code(int(evdev), 1)

    def release(self, evdev: int):
        self.input_redirector.key_event_code(int(evdev), 0)

    def tap(self, evdev: int):
        self.press(evdev)
        self.release(evdev)

    def mods_for_level(self, level: int):
        mods = []
        if level in (1, 3):
            mods.append(KEY_LEFTSHIFT)
        if level in (2, 3):
            mods.append(KEY_RIGHTALT)
        return mods

    def xkb_keycode_to_evdev(self, xkb_keycode: int):
        evdev = int(xkb_keycode) - 8
        return evdev if evdev > 0 else None

    def record_combo_if_absent(self, keysym: int, evdev_key: int, mods: list[int]):
        if keysym not in self.keysym_to_combo:
            self.keysym_to_combo[keysym] = (int(evdev_key), [int(m) for m in mods])

    def build_reverse_map(self):
        km = self.xkb_keymap

        for xkb_keycode in range(self.xkb_min, self.xkb_max + 1):
            evdev = self.xkb_keycode_to_evdev(xkb_keycode)
            if evdev is None:
                continue

            for layout in range(self.xkb_layouts):
                try:
                    nlevels = int(km.num_levels_for_key(xkb_keycode, layout))
                except Exception:
                    nlevels = 4

                # we only support 0..3 levels with our modifier heuristic
                if nlevels > 4:
                    nlevels = 4

                for level in range(nlevels):
                    try:
                        syms = km.key_get_syms_by_level(xkb_keycode, layout, level)
                    except Exception:
                        continue

                    if not syms:
                        continue

                    mods = self.mods_for_level(level)

                    for ks in syms:
                        try:
                            self.record_combo_if_absent(int(ks), evdev, mods)
                        except Exception:
                            continue

    def keyval_name(self, keyval: int) -> str:
        try:
            return Gdk.keyval_name(int(keyval)) or ""
        except Exception:
            return ""

    def normalize_key_name(self, name: str) -> str:
        if not name:
            return ""
        key = str(name).strip()
        lower = key.lower()
        return self.named_keys.get(lower, key)

    def get_named_evdev(self, name: str):
        resolved = self.normalize_key_name(name)

        if resolved in self.modifier_evdev:
            return self.modifier_evdev[resolved], True

        if resolved in self.special_evdev:
            return self.special_evdev[resolved], False

        return None, False

    def press_named_key(self, name: str) -> bool:
        evdev, is_modifier = self.get_named_evdev(name)
        if evdev is None:
            print(f"KeyboardEmulator: unknown named key '{name}'")
            return False

        self.press(evdev)

        if is_modifier:
            self.direct_active_modifiers.add(int(evdev))

        return True

    def release_named_key(self, name: str) -> bool:
        evdev, is_modifier = self.get_named_evdev(name)
        if evdev is None:
            print(f"KeyboardEmulator: unknown named key '{name}'")
            return False

        self.release(evdev)

        if is_modifier:
            self.direct_active_modifiers.discard(int(evdev))

        return True

    def tap_named_key(self, name: str) -> bool:
        evdev, _is_modifier = self.get_named_evdev(name)
        if evdev is None:
            print(f"KeyboardEmulator: unknown named key '{name}'")
            return False

        self.tap(evdev)
        return True

    def press_modifier(self, name: str) -> bool:
        resolved = self.normalize_key_name(name)
        if resolved not in self.modifier_evdev:
            print(f"KeyboardEmulator: '{name}' is not a modifier key")
            return False

        evdev = self.modifier_evdev[resolved]
        self.press(evdev)
        self.direct_active_modifiers.add(int(evdev))
        return True

    def release_modifier(self, name: str) -> bool:
        resolved = self.normalize_key_name(name)
        if resolved not in self.modifier_evdev:
            print(f"KeyboardEmulator: '{name}' is not a modifier key")
            return False

        evdev = self.modifier_evdev[resolved]
        self.release(evdev)
        self.direct_active_modifiers.discard(int(evdev))
        return True

    def tap_special(self, name: str) -> bool:
        resolved = self.normalize_key_name(name)
        if resolved not in self.special_evdev:
            print(f"KeyboardEmulator: '{name}' is not a special key")
            return False

        evdev = self.special_evdev[resolved]
        self.tap(evdev)
        return True

    def release_all_direct_modifiers(self):
        for evdev in reversed(list(self.direct_active_modifiers)):
            self.release(evdev)
        self.direct_active_modifiers.clear()

    def special_combo(self, keyval: int):
        name = self.keyval_name(keyval)

        if name in self.modifier_evdev:
            return self.modifier_evdev[name], []

        if name in self.special_evdev:
            return self.special_evdev[name], []

        # Function keys
        if name.startswith("F") and name[1:].isdigit():
            fn = int(name[1:])
            if 1 <= fn <= 10:
                return 58 + fn, []
            if fn == 11:
                return 87, []
            if fn == 12:
                return 88, []

        return None

    def combo_for_keyval(self, keyval: int):
        # Special keys first
        special = self.special_combo(keyval)
        if special is not None:
            return special

        # Otherwise treat keyval as keysym
        return self.keysym_to_combo.get(int(keyval))

    def on_key_pressed(self, controller, keyval, keycode, state):
        try:
            combo = self.combo_for_keyval(keyval)
            if combo is None:
                name = self.keyval_name(keyval)
                uni = 0
                try:
                    uni = Gdk.keyval_to_unicode(int(keyval)) or 0
                except Exception:
                    uni = 0

                if uni:
                    print(
                        f"Unhandled keysym: {name} keyval={keyval} char={chr(uni)!r} "
                        f"(incoming keycode={keycode}, state={state})"
                    )
                else:
                    print(
                        f"Unhandled keysym: {name} keyval={keyval} "
                        f"(incoming keycode={keycode}, state={state})"
                    )
                return True

            evdev_key, mods = combo

            # Track for release
            active_key = (int(keyval), int(state))
            self.active[active_key] = (int(evdev_key), [int(m) for m in mods])

            # Press mods first, then key
            for m in mods:
                self.press(m)
            self.press(evdev_key)
        except Exception as e:
            name = self.keyval_name(keyval)
            print(f"Error sending key press ({name}, keyval={keyval}, incoming keycode={keycode}): {e}")

        return True

    def on_key_released(self, controller, keyval, keycode, state):
        try:
            active_key = (int(keyval), int(state))
            combo = self.active.pop(active_key, None)

            if combo is None:
                combo = self.combo_for_keyval(keyval)

            if combo is None:
                return False

            evdev_key, mods = combo

            # Release key first, then mods
            self.release(evdev_key)
            for m in reversed(mods):
                self.release(m)
        except Exception as e:
            name = self.keyval_name(keyval)
            print(f"Error sending key release ({name}, keyval={keyval}, incoming keycode={keycode}): {e}")

        return False
