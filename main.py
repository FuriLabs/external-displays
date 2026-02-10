#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>
# Jesús Higueras <jesus@furilabs.com>

import gi
import os

import sys
import time
import subprocess
from asyncio import run, sleep
from gi.repository import GLib, Gio
from external_displays import ExternalDisplays

async def pump_gtk_events():
    main_context = GLib.MainContext.default()

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
