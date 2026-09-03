#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pytest

import cpm80


def test_multiple_drives() -> None:
    a = cpm80.DiskDrive()
    b = cpm80.DiskDrive()

    d = cpm80.StringDisplay()
    m = cpm80.I8080CPMMachine(
        drives=(a, b),
        console_reader=cpm80.StringKeyboard('b:', 'save 1 t.dat', 'a:',
                                            'dir b:', 'dir'),
        console_writer=d)
    m.run()

    # The file is on B: and A: stays empty.
    assert 'B: T        DAT' in d.string
    assert 'NO FILE' in d.string


def test_selecting_missing_drive() -> None:
    d = cpm80.StringDisplay()
    m = cpm80.I8080CPMMachine(console_reader=cpm80.StringKeyboard('c:'),
                              console_writer=d)
    m.run()

    assert 'Bdos Err On C: Select' in d.string


def test_drive_parameters() -> None:
    with pytest.raises(cpm80.Error):
        cpm80.I8080CPMMachine(drives=())

    with pytest.raises(cpm80.Error):
        cpm80.I8080CPMMachine(drives=tuple(cpm80.DiskDrive()
                                           for _ in range(17)))
