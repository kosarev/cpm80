#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80


def test_spec() -> None:
    assert cpm80.DiskImage.parse_header(
        b'cpm80 disk image <https://pypi.org/project/cpm80>\n'
        b'sectors_per_track=40 num_reserved_tracks=2 block_size=2048 '
        b'num_blocks=395 num_dir_entries=128\n\n')['block_size'] == 2048
