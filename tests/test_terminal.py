#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80


def feed(term: cpm80.Terminal, data: bytes) -> tuple[str, bool]:
    # The ANSI text for the whole input, and whether the last byte
    # drew on the screen.
    out = ''
    for c in data:
        out += term.translate(c)
    return out, term.draws_screen


def test_plain_text_is_not_screen_drawing() -> None:
    out, draws = feed(cpm80.ADM3ATerminal(), b'Hi!')
    assert out == 'Hi!'
    assert not draws


def test_control_codes_translate_and_draw() -> None:
    for code, ansi in [(0x1a, '\x1b[2J\x1b[H'), (0x1e, '\x1b[H'),
                       (0x0b, '\x1b[A'), (0x0c, '\x1b[C')]:
        out, draws = feed(cpm80.ADM3ATerminal(), bytes([code]))
        assert out == ansi
        assert draws


def test_cursor_addressing() -> None:
    # ESC = <row+0x20> <col+0x20>; ANSI counts from one.
    out, draws = feed(cpm80.ADM3ATerminal(), b'\x1b=' + bytes([0x25, 0x2a]))
    assert out == '\x1b[6;11H'
    assert draws


def test_unknown_escape_passes_through() -> None:
    out, draws = feed(cpm80.ADM3ATerminal(), b'\x1bZ')
    assert out == '\x1bZ'
    assert not draws


def test_r1715_cursor_addressing() -> None:
    # ESC <row+0x80> <col+0x80>; ANSI counts from one.
    out, draws = feed(cpm80.R1715Terminal(), b'\x1b' + bytes([0x82, 0x85]))
    assert out == '\x1b[3;6H'
    assert draws


def test_r1715_form_feed_clears() -> None:
    out, draws = feed(cpm80.R1715Terminal(), b'\x0c')
    assert out == '\x1b[2J\x1b[H'
    assert draws


def test_r1715_text_passes_through() -> None:
    out, draws = feed(cpm80.R1715Terminal(), b'Hi')
    assert out == 'Hi'
    assert not draws


def test_koi7_maps_cyrillic_and_leaves_ascii() -> None:
    koi7 = cpm80.CHARSETS['koi7']
    assert koi7.translate(0x7b) == 'ш'
    assert koi7.translate(0x69) == 'и'
    assert koi7.translate(ord('A')) == 'A'      # upper-case Latin
    assert koi7.translate(ord(' ')) == ' '


def test_terminal_applies_its_charset_to_text() -> None:
    term = cpm80.R1715Terminal(cpm80.CHARSETS['koi7'])
    out, _ = feed(term, b'priwet')              # KOI-7 for привет
    assert out == 'привет'


def test_default_charset_is_ascii() -> None:
    out, _ = feed(cpm80.ADM3ATerminal(), b'abz')
    assert out == 'abz'
