#!/usr/bin/env python3

import cpm80


def test_default():
    assert cpm80.DiskFormat().disk_size == 800 * 1024
    assert cpm80.DISK_FORMATS['default'].disk_size == 800 * 1024
