#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pytest

import cpm80


def emit(capsys: pytest.CaptureFixture[str], text: bytes) -> str:
    d = cpm80.DisplayDevice()
    for c in text:
        d.output(c)
    return capsys.readouterr().out


def test_plain_text_passes_through(
        capsys: pytest.CaptureFixture[str]) -> None:
    assert emit(capsys, b'Hi!\r\n\tx\x07') == 'Hi!\r\n\tx\x07'


def test_cursor_addressing(capsys: pytest.CaptureFixture[str]) -> None:
    # ESC = <row+0x20> <col+0x20>; ANSI counts rows and columns
    # from one.
    assert emit(capsys, b'\x1b=' + bytes([0x20, 0x20])) == '\x1b[1;1H'
    assert emit(capsys, b'\x1b=' + bytes([0x25, 0x2a])) == '\x1b[6;11H'


def test_control_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert emit(capsys, b'\x1a') == '\x1b[2J\x1b[H'   # clear
    assert emit(capsys, b'\x1e') == '\x1b[H'          # home
    assert emit(capsys, b'\x0b') == '\x1b[A'          # up
    assert emit(capsys, b'\x0c') == '\x1b[C'          # right


def test_unknown_escape_passes_through(
        capsys: pytest.CaptureFixture[str]) -> None:
    assert emit(capsys, b'\x1bZ') == '\x1bZ'
