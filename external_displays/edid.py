# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2025 Furi Labs
#
# Authors:
# Bardia Moshiri <bardia@furilabs.com>

import os

class Edid:
    def __init__(self, edid_array):
        # header information
        self.header              = edid_array[0:8]
        self.manufacturer_id     = edid_array[8:10]
        self.product_code        = edid_array[10:12]
        self.serial_no           = edid_array[12:16]
        self.manufacture_week    = edid_array[16]
        self.manufacture_year    = edid_array[17]
        self.edid_version        = edid_array[18:20]
        # basic display parameters [20-24]
        self.input_params_bitmap = edid_array[20]
        self.h_size_cm           = edid_array[21]
        self.v_size_cm           = edid_array[22]
        self.gamma               = edid_array[23]
        self.features_bitmap     = edid_array[24]
        # chromaticity co-ordinates [25-34]
        self.chroma_coords       = edid_array[25:35]
        # established timing bitmap [35-37]
        self.est_timing_bitmap   = edid_array[35:38]
        # standard timing information [38-53]
        self.display_modes       = edid_array[38:54]
        self.descriptor1         = edid_array[54:72]
        self.descriptor2         = edid_array[72:90]
        self.descriptor3         = edid_array[90:108]
        self.descriptor4         = edid_array[108:126]
        self.num_extensions      = edid_array[126]
        self.checksum            = edid_array[127]

def parse_mfct_id(code):
    id_hex = int(''.join(code), base=16)
    char1 = chr(((id_hex >> 00) & (0x001F)) + 0x40)
    char2 = chr(((id_hex >>  5) & (0x001F)) + 0x40)
    char3 = chr(((id_hex >> 10) & (0x001F)) + 0x40)
    return ''.join([char3, char2, char1])

def read_edid_file(filename):
    try:
        with open(filename, 'rb') as edid_file:
            edid_raw = edid_file.read(128)  # Read only the first 128 bytes
            edid_formatted = [f"{byte:02X}" for byte in edid_raw]
        return edid_formatted
    except Exception as e:
        print(f"Error reading EDID file: {e}")
        return None

def get_display_info(card_path="card1", connector="DVI-I-1"):
    """
    Get display information from sysfs

    Returns:
        dict with status, power_state, and manufacturer information
    """
    base_path = f"/sys/class/drm/{card_path}/{card_path}-{connector}"

    if not os.path.exists(base_path):
        return {
            'status': 'Not Found',
            'power_state': 'Unknown',
            'manufacturer': ''
        }

    try:
        with open(f"{base_path}/status", 'r') as f:
            status = f.read().strip()
    except:
        status = 'Unknown'

    try:
        with open(f"{base_path}/dpms", 'r') as f:
            power_state = f.read().strip()
    except:
        power_state = 'Unknown'

    edid_path = f"{base_path}/edid"
    if os.path.exists(edid_path):
        edid_array = read_edid_file(edid_path)
        if edid_array:
            edid = Edid(edid_array)
            manufacturer = parse_mfct_id(edid.manufacturer_id)
        else:
            manufacturer = 'Error'
    else:
        manufacturer = ''

    return {
        'status': status,
        'power_state': power_state,
        'manufacturer': manufacturer
    }
