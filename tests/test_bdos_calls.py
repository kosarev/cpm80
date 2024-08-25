#!/usr/bin/env python3

import cpm80
import pytest


def test_c_writestr(capsys):
    m = cpm80.I8080CPMMachine()
    m.write_str('abc')
    assert capsys.readouterr().out == 'abc'


def test_s_bdosver():
    m = cpm80.I8080CPMMachine()

    CPM_VERSION_2_2 = 0x22
    MACHINE_TYPE_8080 = 0
    CPM_TYPE_PLAIN = 0
    assert m.get_bdos_version() == (CPM_VERSION_2_2, MACHINE_TYPE_8080,
                                    CPM_TYPE_PLAIN)


def test_file_read_write():
    m = cpm80.I8080CPMMachine()
    m.make_file('file.bin')
    m.write_file(b'abc')
    m.close_file()

    m.open_file('file.bin')
    assert m.read_file(0) == b''
    assert m.read_file() == b'abc' + b'\x1a' * (cpm80.SECTOR_SIZE - 3)
    m.close_file()


def test_file_rename():
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
