#!/usr/bin/env python3

import cpm80
import pytest


def test_basic():
    assert cpm80.DiskFormat().disk_size == 800 * 1024
    assert cpm80.DISK_FORMATS['default'].disk_size == 800 * 1024
    assert cpm80.DISK_FORMATS['korvet'].disk_size == 798 * 1024

    with pytest.raises(cpm80.Error):
        cpm80.DiskFormat(block_size=1024, num_blocks=0x101)


def test_spec():
    assert cpm80.DiskFormat.parse_spec([
        'sectors_per_track=40',
        'num_reserved_tracks=2',
        'block_size=2048',
        'num_blocks=395',
        'num_dir_entries=128'])['block_size'] == 2048
