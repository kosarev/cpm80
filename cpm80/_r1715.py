#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""The Robotron 1715: a Z80 CP/M with the R1715 terminal and glyphs.

The machine registers itself in the package's MACHINES table when
imported, so --r1715 finds it.
"""

import collections.abc

from . import (
    DISK_FORMATS,
    MACHINES,
    Charset,
    ConsoleReader,
    ConsoleWriter,
    DiskDrive,
    DisplayDevice,
    Z80CPMMachine,
)

# The Robotron 1715 glyphs that differ from ASCII: capital Cyrillic
# where ASCII has the lower-case letters and the symbols after them
# (the KOI-7 N2 layout, GOST 13052), and a solid block at 0xff that
# its games fill the screen with.
_GLYPHS = {
    0x60: 'Ю', 0x61: 'А', 0x62: 'Б', 0x63: 'Ц', 0x64: 'Д', 0x65: 'Е',
    0x66: 'Ф', 0x67: 'Г', 0x68: 'Х', 0x69: 'И', 0x6a: 'Й', 0x6b: 'К',
    0x6c: 'Л', 0x6d: 'М', 0x6e: 'Н', 0x6f: 'О', 0x70: 'П', 0x71: 'Я',
    0x72: 'Р', 0x73: 'С', 0x74: 'Т', 0x75: 'У', 0x76: 'Ж', 0x77: 'В',
    0x78: 'Ь', 0x79: 'Ы', 0x7a: 'З', 0x7b: 'Ш', 0x7c: 'Э', 0x7d: 'Щ',
    0x7e: 'Ч', 0x7f: 'Ъ',
    0xff: '█',
}
CHARSET = Charset(_GLYPHS)


# The Robotron 1715 terminal.  Its cursor addressing is ESC followed
# by a row byte and a column byte, each biased by 0x80.  Form feed
# clears the screen.  Its games draw the screen as a plain run of
# characters and rely on the terminal to wrap to the next line at the
# right edge, so this tracks the cursor column and wraps at the
# screen width.  This covers what the R1715 games observed emit; their
# Cyrillic text is handled by the character set.
class R1715Terminal:
    __WIDTH = 80

    # Waiting for the rest of a sequence: 0 none, 1 want the row byte,
    # 2 want the column byte.
    def __init__(self, charset: Charset | None = None) -> None:
        self.__charset = charset if charset is not None else Charset({})
        self.__pending = 0
        self.__row = 0
        self.__col = 0
        self.draws_screen = False

    def translate(self, c: int) -> str:
        self.draws_screen = False

        if self.__pending == 1:
            self.__row = c
            self.__pending = 2
            return ''

        if self.__pending == 2:
            # The row and column are biased by 0x80; ANSI counts from
            # one.
            row = max(0, self.__row - 0x80) + 1
            col = max(0, c - 0x80) + 1
            self.__pending = 0
            self.__col = col - 1
            self.draws_screen = True
            return f'\x1b[{row};{col}H'

        if c == 0x1b:               # ESC introduces a cursor position
            self.__pending = 1
            return ''
        if c == 0x0c:               # form feed clears the screen
            self.__col = 0
            self.draws_screen = True
            return '\x1b[2J\x1b[H'
        if c == 0x0d:               # carriage return
            self.__col = 0
            return '\r'
        if c < 0x20:                # other controls do not move the column
            return self.__charset.translate(c)

        # A printable character.  Wrap to the next line before it if
        # the row is full.
        prefix = ''
        if self.__col >= self.__WIDTH:
            prefix = '\r\n'
            self.__col = 0
        self.__col += 1
        return prefix + self.__charset.translate(c)


# The Z80 core wired to the R1715 disk format and, via its default
# display, the R1715 terminal and character set.
class R1715Machine(Z80CPMMachine):
    disk_format = DISK_FORMATS['r1715']

    def __init__(self, *,
                 drives: collections.abc.Sequence[DiskDrive] | None = None,
                 console_reader: ConsoleReader | None = None,
                 console_writer: ConsoleWriter | None = None,
                 speed_mhz: float | None = None) -> None:
        if console_writer is None:
            console_writer = DisplayDevice(terminal=R1715Terminal(CHARSET))
        super().__init__(drives=drives, console_reader=console_reader,
                         console_writer=console_writer, speed_mhz=speed_mhz)


MACHINES['r1715'] = R1715Machine
