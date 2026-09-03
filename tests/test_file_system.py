#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pytest

import cpm80


def test_round_trip() -> None:
    fs = cpm80.FileSystem(cpm80.DiskImage(cpm80.DiskFormat()))
    fs.write('a.txt', b'abc')

    assert fs.names() == ['A.TXT']
    assert fs.read('a.txt') == b'abc' + b'\x1a' * (cpm80.SECTOR_SIZE - 3)

    # The image is an ordinary disk a machine can use.
    m = cpm80.I8080CPMMachine(drives=[cpm80.DiskDrive(fs.image)])
    m.open_file('a.txt')
    assert m.read_file().startswith(b'abc')
    m.close_file()


def test_reading_pre_existing_image() -> None:
    drive = cpm80.DiskDrive()
    m = cpm80.I8080CPMMachine(drives=[drive])
    m.make_file('made.txt')
    m.write_file(b'made outside')
    m.close_file()

    fs = cpm80.FileSystem(drive.image)
    assert fs.names() == ['MADE.TXT']
    assert fs.read('made.txt').startswith(b'made outside')


def test_delete() -> None:
    fs = cpm80.FileSystem(cpm80.DiskImage(cpm80.DiskFormat()))
    fs.write('a.txt', b'abc')
    fs.delete('a.txt')

    assert fs.names() == []
    with pytest.raises(cpm80.Error):
        fs.read('a.txt')


def test_no_partial_files_on_full_disk() -> None:
    format = cpm80.DiskFormat(block_size=1024, num_blocks=8,
                              num_dir_entries=32)
    fs = cpm80.FileSystem(cpm80.DiskImage(format))

    with pytest.raises(cpm80.Error, match='cannot write file'):
        fs.write('big.dat', b'x' * 8 * 1024)

    assert fs.names() == []
    fs.write('small.dat', b'y' * 1024)
    assert fs.names() == ['SMALL.DAT']


def test_no_directory_space() -> None:
    format = cpm80.DiskFormat(block_size=1024, num_blocks=8,
                              num_dir_entries=32)
    fs = cpm80.FileSystem(cpm80.DiskImage(format))

    for i in range(32):
        fs.write(f'f{i}', b'')

    with pytest.raises(cpm80.Error, match='no directory space'):
        fs.write('extra', b'')
