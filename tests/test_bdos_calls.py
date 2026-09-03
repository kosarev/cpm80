#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pytest

import cpm80


def test_c_writestr(capsys: pytest.CaptureFixture[str]) -> None:
    m = cpm80.I8080CPMMachine()
    m.write_str('abc')
    assert capsys.readouterr().out == 'abc'


def test_s_bdosver() -> None:
    m = cpm80.I8080CPMMachine()

    CPM_VERSION_2_2 = 0x22
    MACHINE_TYPE_8080 = 0
    CPM_TYPE_PLAIN = 0
    assert m.get_bdos_version() == (CPM_VERSION_2_2, MACHINE_TYPE_8080,
                                    CPM_TYPE_PLAIN)


def test_file_read_write() -> None:
    m = cpm80.I8080CPMMachine()
    m.make_file('file.bin')
    m.write_file(b'abc')
    m.close_file()

    m.open_file('file.bin')
    assert m.read_file(0) == b''
    assert m.read_file() == b'abc' + b'\x1a' * (cpm80.SECTOR_SIZE - 3)
    m.close_file()


def test_file_rename() -> None:
    m = cpm80.I8080CPMMachine()
    m.make_file('file.bin')
    m.close_file()

    with pytest.raises(cpm80.Error):
        m.rename_file('xfile.bin', 'file2.bin')

    m.rename_file('file.bin', 'file2.bin')

    with pytest.raises(cpm80.Error):
        m.open_file('file.bin')

    m.open_file('file2.bin')
    assert m.read_file() == b''

    # TODO: Test deleting the file.
