#!/usr/bin/env python3

import cpm80
import pytest


def test_basic():
    assert cpm80.DiskFormat().disk_size == 800 * 1024
    assert cpm80.DISK_FORMATS['default'].disk_size == 800 * 1024
    assert cpm80.DISK_FORMATS['korvet'].disk_size == 798 * 1024

    with pytest.raises(cpm80.Error):
        cpm80.DiskFormat(block_size=1024, num_blocks=0x101)