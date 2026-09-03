#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pathlib

import pytest

import cpm80


def test_mount(tmp_path: pathlib.Path) -> None:
    (tmp_path / 'hello.txt').write_bytes(b'hello')
    (tmp_path / 'empty.dat').write_bytes(b'')
    (tmp_path / 'noext').write_bytes(b'x')
    (tmp_path / '.hidden').write_bytes(b'x')
    (tmp_path / 'subdir').mkdir()

    drive = cpm80.HostDrive(tmp_path)

    assert drive.host_paths == {
        'HELLO.TXT': tmp_path / 'hello.txt',
        'EMPTY.DAT': tmp_path / 'empty.dat',
        'NOEXT': tmp_path / 'noext'}
    assert drive.warnings == []

    m = cpm80.I8080CPMMachine(drives=[drive])
    m.open_file('hello.txt')
    assert m.read_file() == b'hello' + b'\x1a' * (cpm80.SECTOR_SIZE - 5)
    m.close_file()

    m.open_file('empty.dat')
    assert m.read_file() == b''
    m.close_file()


def test_invalid_and_conflicting_names(
        tmp_path: pathlib.Path) -> None:
    (tmp_path / 'A.TXT').write_bytes(b'x')
    (tmp_path / 'a.txt').write_bytes(b'y')
    (tmp_path / 'toolongname.txt').write_bytes(b'z')
    (tmp_path / 'file.text').write_bytes(b'z')
    (tmp_path / 'my file.txt').write_bytes(b'z')
    (tmp_path / 'archive.tar.gz').write_bytes(b'z')

    drive = cpm80.HostDrive(tmp_path)

    assert list(drive.host_paths) == ['A.TXT']
    assert drive.host_paths['A.TXT'] == tmp_path / 'A.TXT'
    assert any('a.txt' in w and 'already taken' in w
               for w in drive.warnings)
    for name in ('toolongname.txt', 'file.text', 'my file.txt',
                 'archive.tar.gz'):
        assert any(name in w and 'not a valid CP/M filename' in w
                   for w in drive.warnings)


def test_capacity(tmp_path: pathlib.Path) -> None:
    (tmp_path / 'small.dat').write_bytes(b'x' * 1024)
    (tmp_path / 'toobig.dat').write_bytes(b'y' * 8 * 1024)

    # 8 blocks of 1K with one taken by the directory.
    format = cpm80.DiskFormat(block_size=1024, num_blocks=8,
                              num_dir_entries=32)
    drive = cpm80.HostDrive(tmp_path, format=format)

    assert list(drive.host_paths) == ['SMALL.DAT']
    assert any('toobig.dat' in w and 'no space left' in w
               for w in drive.warnings)


def test_remount(tmp_path: pathlib.Path) -> None:
    (tmp_path / 'a.txt').write_bytes(b'a')
    drive = cpm80.HostDrive(tmp_path)
    assert list(drive.host_paths) == ['A.TXT']

    (tmp_path / 'b.txt').write_bytes(b'b')
    drive.remount()
    assert list(drive.host_paths) == ['A.TXT', 'B.TXT']


def test_missing_directory(tmp_path: pathlib.Path) -> None:
    with pytest.raises(cpm80.Error):
        cpm80.HostDrive(tmp_path / 'nonexistent')
