#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pytest

import cpm80


def test_commands(capsys: pytest.CaptureFixture[str]) -> None:
    cpm80.main(['--temp-disk', 'dir'])
    assert capsys.readouterr().out == '\r\nA>dir\r\r\nNO FILE\r\nA>'
