#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pytest

import cpm80


def test_spec() -> None:
    assert cpm80.DiskImage.parse_header(
        b'cpm80 disk image <https://pypi.org/project/cpm80>\n'
        b'sectors_per_track=40 num_reserved_tracks=2 block_size=2048 '
        b'num_blocks=395 num_dir_entries=128\n\n')['block_size'] == 2048


def test_bad_header() -> None:
    # A foreign image with no signature.
    with pytest.raises(cpm80.Error):
        cpm80.DiskImage.parse_header(b'\xe5' * 256)

    # A signature followed by an undecodable header.
    with pytest.raises(cpm80.Error):
        cpm80.DiskImage.parse_header(
            b'cpm80 disk image <https://pypi.org/project/cpm80>\n'
            b'\xe5\xe5\n\n')


def test_sector_bounds() -> None:
    image = cpm80.DiskImage(cpm80.DiskFormat())

    # The default format is 1001 tracks of 64 sectors.
    assert len(image.get_sector(63, 1000)) == cpm80.SECTOR_SIZE

    for sector, track in (64, 0), (0, 1001), (-1, 0), (0, -1):
        with pytest.raises(cpm80.Error):
            image.get_sector(sector, track)


def test_data_size_mismatch() -> None:
    format = cpm80.DiskFormat()

    with pytest.raises(cpm80.Error):
        cpm80.DiskImage(format, data=b'x' * 1000)

    image = cpm80.DiskImage(format, data=bytes(format.disk_size))
    assert len(image.data) == format.disk_size
