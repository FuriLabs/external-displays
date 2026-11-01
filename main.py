#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2026 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>
# Jesús Higueras <jesus@furilabs.com>

from external_displays import ExternalDisplays

if __name__ == "__main__":
    app = ExternalDisplays(application_id="io.furios.ExternalDisplays")
    app.run()
