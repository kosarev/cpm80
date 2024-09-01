#!/usr/bin/env python3

import cpm80


def test_spec():
    assert cpm80.DiskImage.parse_header(
        b'# cpm80 --sectors-per-track=40 --num-reserved-tracks=2 '
        b'--block-size=2048 --num-blocks=395 '
        b'--num-dir-entries=128')['block_size'] == 2048
