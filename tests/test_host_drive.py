#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import os
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


def test_flush_new_and_updated_files(tmp_path: pathlib.Path) -> None:
    (tmp_path / 'old.txt').write_bytes(b'old')
    drive = cpm80.HostDrive(tmp_path)

    m = cpm80.I8080CPMMachine(drives=[drive])
    m.make_file('new.txt')
    m.write_file(b'created inside')
    m.close_file()

    m.open_file('old.txt')
    m.write_file(b'updated!')
    m.close_file()

    drive.flush_files()

    PAD = b'\x1a'
    assert ((tmp_path / 'new.txt').read_bytes() ==
            b'created inside' + PAD * (cpm80.SECTOR_SIZE - 14))
    assert ((tmp_path / 'old.txt').read_bytes() ==
            b'updated!' + PAD * (cpm80.SECTOR_SIZE - 8))
    assert drive.host_paths['NEW.TXT'] == tmp_path / 'new.txt'


def test_flush_skips_unchanged_files(tmp_path: pathlib.Path) -> None:
    path = tmp_path / 'keep.txt'
    path.write_bytes(b'keep')
    drive = cpm80.HostDrive(tmp_path)

    os.utime(path, ns=(0, 0))
    drive.flush_files()

    # Not rewritten, and in particular not re-padded.
    assert path.stat().st_mtime_ns == 0
    assert path.read_bytes() == b'keep'


def test_flush_never_deletes_host_files(
        tmp_path: pathlib.Path) -> None:
    (tmp_path / 'a.txt').write_bytes(b'a')
    drive = cpm80.HostDrive(tmp_path)

    m = cpm80.I8080CPMMachine(
        drives=[drive],
        console_reader=cpm80.StringKeyboard('era a.txt'),
        console_writer=cpm80.StringDisplay())
    m.run()

    # The erasure triggers a flush by itself; the host file stays.
    assert (tmp_path / 'a.txt').read_bytes() == b'a'


def test_flush_on_close(tmp_path: pathlib.Path) -> None:
    drive = cpm80.HostDrive(tmp_path)
    m = cpm80.I8080CPMMachine(drives=[drive])

    # The file appears on the host as CP/M commits it, with no
    # explicit flush.
    m.make_file('x.txt')
    m.write_file(b'x')
    m.close_file()

    assert ((tmp_path / 'x.txt').read_bytes() ==
            b'x' + b'\x1a' * (cpm80.SECTOR_SIZE - 1))


def test_warm_boot_flushes_and_remounts(
        tmp_path: pathlib.Path) -> None:
    drive = cpm80.HostDrive(tmp_path)
    m = cpm80.I8080CPMMachine(drives=[drive])

    m.make_file('born.txt')
    m.write_file(b'born')
    m.close_file()

    (tmp_path / 'late.txt').write_bytes(b'late')
    m.on_wboot()

    # The late host file is mounted now, and the file born on the
    # drive survived the flush and the re-mount.
    assert sorted(drive.host_paths) == ['BORN.TXT', 'LATE.TXT']
    m.open_file('late.txt')
    assert m.read_file().startswith(b'late')
    m.close_file()


def test_flush_multi_extent_files(tmp_path: pathlib.Path) -> None:
    content = bytes(range(256)) * 80
    (tmp_path / 'big.bin').write_bytes(content)

    # 8-bit block pointers, one 16K logical extent per directory
    # entry, so the file spans two entries.
    format = cpm80.DiskFormat(block_size=1024, num_blocks=100)
    drive = cpm80.HostDrive(tmp_path, format=format)

    (tmp_path / 'big.bin').unlink()
    drive.flush_files()
    assert (tmp_path / 'big.bin').read_bytes() == content
