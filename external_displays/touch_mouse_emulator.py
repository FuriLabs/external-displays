# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
import time

from external_displays.input_redirector import InputRedirector

# Linux input event codes
BTN_LEFT = 272
BTN_RIGHT = 273

class TouchMouseEmulator:
    def __init__(self, drawing_area, app):
        self.drawing_area = drawing_area
        self.app = app

        # Input redirector
        self.input_redirector = InputRedirector(source="app:external-displays")

        self.sensitivity = 4.0

        # Movement threshold to prevent accidental clicks
        self.movement_threshold = 10.0  # Pixels of movement required to consider it a drag, not a tap

        # Flag to track if we've moved enough to consider it a drag
        self.has_moved_threshold = False

        # Flag to track if we're in gesture drag mode
        self.is_gesture_dragging = False

        self.touch_active = False
        self.touch_x = 0
        self.touch_y = 0

        # Setup controllers for input events
        self.gesture_click = Gtk.GestureClick.new()
        self.gesture_click.set_button(0)
        self.gesture_click.connect("pressed", self.on_press)
        self.gesture_click.connect("released", self.on_release)
        self.drawing_area.add_controller(self.gesture_click)

        self.gesture_drag = Gtk.GestureDrag.new()
        self.gesture_drag.connect("drag-begin", self.on_drag_begin)
        self.gesture_drag.connect("drag-update", self.on_drag_update)
        self.gesture_drag.connect("drag-end", self.on_drag_end)
        self.drawing_area.add_controller(self.gesture_drag)

        # Setup touch gesture
        self.touch_controller = Gtk.GestureZoom.new()
        self.touch_controller.connect("begin", self.on_zoom_begin)
        self.touch_controller.connect("scale-changed", self.on_zoom_scale_changed)
        self.drawing_area.add_controller(self.touch_controller)

        self.is_dragging = False
        self.drag_start_pos = None
        self.last_touch_time = 0
        self.touch_hold_timer = None
        self.active_touches = {}
        self.last_scale = 1.0

        # Cumulative movement tracker for drag detection
        self.total_movement = 0.0

        # Track last positions for delta calculation
        self.last_x = 0
        self.last_y = 0

    def on_draw(self, area, cr, width, height):
        # Draw background
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Draw grid lines for orientation
        cr.set_source_rgb(0.8, 0.8, 0.8)
        cr.set_line_width(1)

        # Vertical lines
        step_x = max(1, width // 10)
        for x in range(0, width, step_x):
            cr.move_to(x, 0)
            cr.line_to(x, height)
            cr.stroke()

        # Horizontal lines
        step_y = max(1, height // 10)
        for y in range(0, height, step_y):
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

        # Draw center cross
        cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.set_line_width(2)
        cr.move_to(width / 2 - 20, height / 2)
        cr.line_to(width / 2 + 20, height / 2)
        cr.stroke()
        cr.move_to(width / 2, height / 2 - 20)
        cr.line_to(width / 2, height / 2 + 20)
        cr.stroke()

        # Draw touch indicator
        if self.touch_active:
            cr.set_source_rgb(1.0, 0.0, 0.0)
            cr.arc(self.touch_x, self.touch_y, 10, 0, 2 * 3.14159)
            cr.fill()

        return False

    def tap_button(self, btn_code):
        self.input_redirector.mouse_button(btn_code, 1)
        self.input_redirector.mouse_button(btn_code, 0)

    def scroll_step(self, direction):
        val = 1 if direction == "down" else -1
        self.input_redirector.scroll(self.REL_WHEEL, val)

    def on_press(self, gesture, n_press, x, y):
        button = gesture.get_current_button()

        # Touch indicator
        self.touch_active = True
        self.touch_x = x
        self.touch_y = y
        self.drawing_area.queue_draw()

        # Reset movement tracking on press
        self.has_moved_threshold = False
        self.total_movement = 0.0

        # Store drag starting reference
        self.drag_start_pos = (x, y)
        self.last_x = x
        self.last_y = y

        # Handle mouse button press events
        if button == 1:  # Left
            current_time = time.time()
            if n_press == 2:
                # Double click
                self.tap_button(BTN_LEFT)
                self.tap_button(BTN_LEFT)
                self.last_touch_time = 0
            else:
                self.last_touch_time = current_time

                # Start timer for drag and drop
                if self.touch_hold_timer:
                    GLib.source_remove(self.touch_hold_timer)
                self.touch_hold_timer = GLib.timeout_add(300, self.on_touch_hold)
        elif button == 3:  # Right
            self.tap_button(BTN_RIGHT)

    def on_release(self, gesture, n_press, x, y):
        button = gesture.get_current_button()

        self.touch_active = False
        self.drawing_area.queue_draw()

        # Cancel hold timer if active
        if self.touch_hold_timer:
            GLib.source_remove(self.touch_hold_timer)
            self.touch_hold_timer = None

        # Handle left button (1) clicks
        if button == 1:
            # Only do a click if:
            # 1. We haven't moved much
            # 2. We're not in drag mode
            # 3. We're not in gesture drag mode
            if not self.has_moved_threshold and not self.is_dragging and not self.is_gesture_dragging:
                # Simple click
                self.tap_button(BTN_LEFT)
            elif self.is_dragging:
                # End drag if we were dragging
                self.input_redirector.mouse_button(BTN_LEFT, 0)
                self.is_dragging = False

        # Clean up state
        self.drag_start_pos = None

        # Reset movement tracking
        self.has_moved_threshold = False
        self.total_movement = 0.0

    def on_touch_hold(self):
        # Only start drag if we haven't moved much (to prevent accidental drags)
        if not self.has_moved_threshold:
            # Start drag operation where the cursor currently is
            self.input_redirector.mouse_button(BTN_LEFT, 1)
            self.is_dragging = True

        self.touch_hold_timer = None
        return GLib.SOURCE_REMOVE

    def on_drag_begin(self, gesture, start_x, start_y):
        # Start position for the drag
        self.drag_start_pos = (start_x, start_y)
        self.is_gesture_dragging = True

        self.touch_active = True
        self.touch_x = start_x
        self.touch_y = start_y

        self.last_x = start_x
        self.last_y = start_y

        # Reset movement tracking
        self.has_moved_threshold = False
        self.total_movement = 0.0

        self.drawing_area.queue_draw()

        # Cancel hold timer if active
        if self.touch_hold_timer:
            GLib.source_remove(self.touch_hold_timer)
            self.touch_hold_timer = None

    def on_drag_update(self, gesture, offset_x, offset_y):
        if not self.drag_start_pos:
            return

        # Get current position from start position and offset
        start_x, start_y = self.drag_start_pos
        current_x = start_x + offset_x
        current_y = start_y + offset_y

        self.touch_x = current_x
        self.touch_y = current_y

        # Delta since last update
        delta_x = current_x - self.last_x
        delta_y = current_y - self.last_y

        # Calculate the Total movement
        total_offset = (offset_x ** 2 + offset_y ** 2) ** 0.5
        self.total_movement += total_offset

        # If we've moved enough, mark as a movement, not a tap
        if self.total_movement > self.movement_threshold and not self.has_moved_threshold:
            self.has_moved_threshold = True

            # Cancel hold timer if we start moving
            if self.touch_hold_timer:
                GLib.source_remove(self.touch_hold_timer)
                self.touch_hold_timer = None

        self.last_x = current_x
        self.last_y = current_y

        # Scale deltas
        scaled_dx = self.scale_delta_x(delta_x, 0)
        scaled_dy = self.scale_delta_y(delta_y, 0)

        if abs(scaled_dx) < 1 and abs(scaled_dy) < 1:
            return

        # Move cursor relatively
        self.input_redirector.mouse_motion(scaled_dx, scaled_dy)

        self.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        self.touch_active = False
        self.drawing_area.queue_draw()

        # Calculate total movement distance
        total_distance = (offset_x ** 2 + offset_y ** 2) ** 0.5

        # Mark as moved if distance is significant (ensure click doesn't happen after drag)
        if total_distance > self.movement_threshold / 2:
            self.has_moved_threshold = True

        # If this was a drag operation, clean up
        if self.is_dragging:
            self.input_redirector.mouse_button(BTN_LEFT, 0)
            self.is_dragging = False

        # Reset this gesture state
        self.is_gesture_dragging = False
        self.drag_start_pos = None

    def on_zoom_begin(self, gesture, sequence):
        # Starting two-finger operation
        self.last_scale = 1.0

    def on_zoom_scale_changed(self, gesture, scale):
        # Handle zoom gestures (for scrolling)
        delta_scale = scale - self.last_scale

        if abs(delta_scale) > 0.05: # Threshold to avoid jitter
            scroll_direction = "down" if delta_scale < 0 else "up"
            scroll_amount = min(abs(int(delta_scale * 10)), 5)

            for _ in range(scroll_amount):
                self.scroll_step(scroll_direction)

            self.last_scale = scale

    def scale_delta_x(self, delta_x, width):
        if delta_x == 0:
            return 0

        scaled = delta_x * self.sensitivity

        if abs(scaled) > 50:
            return 50 if scaled > 0 else -50

        return int(scaled)

    def scale_delta_y(self, delta_y, height):
        if delta_y == 0:
            return 0

        scaled = delta_y * self.sensitivity

        if abs(scaled) > 50:
            return 50 if scaled > 0 else -50

        return int(scaled)

    def clear_touch_state(self):
        self.active_touches = {}

        if self.touch_hold_timer:
            GLib.source_remove(self.touch_hold_timer)
            self.touch_hold_timer = None

        if self.is_dragging:
            self.input_redirector.mouse_button(BTN_LEFT, 0)
            self.is_dragging = False
