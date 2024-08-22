#!/usr/bin/env python3

import cpm80


def test_default():
    f = cpm80.DiskFormat()
    assert f.disk_size == 800 * 1024
