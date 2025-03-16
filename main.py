#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2025 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>
# Jesús Higueras <jesus@furilabs.com>

import gi
import os

# We set DISPLAY to make xdotool and xrandr work for display management, but always show the app in Wayland Phosh
os.environ['GDK_BACKEND'] = 'wayland'

import sys
import time
import subprocess
from asyncio import run, sleep
from gi.repository import GLib, Gio
from external_displays import ExternalDisplays

def check_dependencies():
    try:
        subprocess.run(["which", "xdotool"], check=True, stdout=subprocess.PIPE)
    except subprocess.CalledProcessError:
        print("Error: xdotool is not installed")
        sys.exit(1)

async def pump_gtk_events():
    main_context = GLib.MainContext.default()

    if len(sys.argv) > 1:
        os.environ['DISPLAY'] = sys.argv[1]
        print(f"Overriding DISPLAY with: {sys.argv[1]}")
    elif 'DISPLAY' not in os.environ:
        os.environ['DISPLAY'] = ':1'
        print("DISPLAY not set, defaulting to :1")

    check_dependencies()

    app = ExternalDisplays(application_id="io.furios.ExternalDisplays")
    app.connect('shutdown', lambda _: exit(0))

    Gio.Application.set_default(app)
    app.register()
    app.activate()

    frame_time = 1 / (240)

    while True:
        start_time = time.time()

        while main_context.pending():
            main_context.iteration(False)

        elapsed = time.time() - start_time
        remaining = max(0, frame_time - elapsed)

        if remaining > 0:
            await sleep(remaining)

if __name__ == "__main__":
    run(pump_gtk_events())
