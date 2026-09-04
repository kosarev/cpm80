#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import collections.abc
import contextlib
import os
import sys
import typing

if sys.platform == 'win32':
    import msvcrt
else:
    import select
    import termios
    import tty


class KeyboardDevice:
    def __init__(self) -> None:
        self.__ctrl_c_count = 0

    def input(self) -> int | None:
        # The terminal is put in raw mode for the whole session (see
        # _console_session), so a key is read straight from the file
        # descriptor -- matching the descriptor-level ready() check,
        # and without the mode change that would discard it.
        if sys.platform == 'win32':
            # Note that Ctrl+C comes as an ordinary character and
            # special keys come as two reads with a 0x00 or 0xe0
            # prefix, undecoded, just as escape sequences on Unix.
            ch = ord(msvcrt.getch())
        else:
            data = os.read(sys.stdin.fileno(), 1)
            if not data:
                return None     # end of input
            ch = data[0]

        # Catch Ctrl+C.
        if ch == 3:
            self.__ctrl_c_count += 1
            if self.__ctrl_c_count >= 3:
                return None
        else:
            self.__ctrl_c_count = 0

        # Translate backspace.
        if ch == 127:
            ch = 8

        return ch

    def ready(self) -> bool:
        # Only an interactive terminal has keys waiting; a
        # redirected or captured stdin never does, and polling it
        # would misreport its end as a waiting character.
        try:
            if not sys.stdin.isatty():
                return False
        except (OSError, ValueError):
            return False

        if sys.platform == 'win32':
            return msvcrt.kbhit()
        else:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            return bool(readable)


class StringKeyboard:
    def __init__(self, *commands: str) -> None:
        self.__input = '\n'.join(commands) + '\n'
        self.__i = 0

    def input(self) -> int | None:
        if self.__i >= len(self.__input):
            return None

        c = self.__input[self.__i]
        self.__i += 1
        return ord(c)

    # Never reports a key waiting: the commands are delivered one at
    # a time only when the machine reads, never typed ahead.  A
    # reader that reported ready while commands remain would have
    # them consumed by CP/M's console-status polling during output.
    def ready(self) -> bool:
        return False


# Translates the control codes a CP/M program emits for its terminal
# into ANSI for the host terminal.  A machine selects which terminal
# it emulates.  translate() returns the display text for one output
# byte: its own character, mapped through the terminal's glyphs, or
# the ANSI for a control code.  After a byte that moves or clears the
# cursor it sets draws_screen, so the display can hide the blinking
# hardware cursor while a program paints the screen.
class Terminal(typing.Protocol):
    draws_screen: bool

    def translate(self, c: int) -> str:
        ...


# The ADM-3A, the terminal the bundled CP/M expects.  Its glyphs are
# plain ASCII.
class ADM3ATerminal:
    # Waiting for the rest of an escape sequence: 0 none, 1 seen
    # ESC, 2 want the row byte, 3 want the column byte.
    def __init__(self) -> None:
        self.__pending = 0
        self.__row = 0
        self.draws_screen = False

    def translate(self, c: int) -> str:
        self.draws_screen = False

        if self.__pending == 1:
            if c == ord('='):       # ESC= loads the cursor position
                self.__pending = 2
                return ''
            # some other escape; pass it on
            self.__pending = 0
            return '\x1b' + chr(c)

        if self.__pending == 2:
            self.__row = c
            self.__pending = 3
            return ''

        if self.__pending == 3:
            # The row and column are biased by a space; ANSI counts
            # from one.
            row = max(0, self.__row - 0x20) + 1
            col = max(0, c - 0x20) + 1
            self.__pending = 0
            self.draws_screen = True
            return f'\x1b[{row};{col}H'

        SEQUENCES = {
            0x0b: '\x1b[A',         # cursor up
            0x0c: '\x1b[C',         # cursor right
            0x1a: '\x1b[2J\x1b[H',  # clear screen and home
            0x1e: '\x1b[H',         # home
        }
        if c == 0x1b:               # ESC
            self.__pending = 1
            return ''
        if c in SEQUENCES:
            self.draws_screen = True
            return SEQUENCES[c]
        return chr(c)


# Writes a terminal's output to the host tty and manages the hardware
# cursor.  The translation itself is the terminal's; this is the sink.
class DisplayDevice:
    def __init__(self, terminal: Terminal | None = None) -> None:
        self.__terminal = terminal if terminal is not None else ADM3ATerminal()
        self.__cursor_hidden = False

    def __write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    # A program that positions the cursor is drawing a screen; hide
    # the hardware cursor so it does not blink chasing the writes.
    # show_cursor() brings it back when control returns to CCP (see
    # on_wboot) and when the session ends.
    def __hide_cursor(self) -> None:
        if not self.__cursor_hidden:
            self.__write('\x1b[?25l')
            self.__cursor_hidden = True

    def show_cursor(self) -> None:
        if self.__cursor_hidden:
            self.__write('\x1b[?25h')
            self.__cursor_hidden = False

    def output(self, c: int) -> None:
        text = self.__terminal.translate(c)
        if self.__terminal.draws_screen:
            self.__hide_cursor()
        if text:
            self.__write(text)


class StringDisplay:
    def __init__(self) -> None:
        self.__output: list[int] = []

    def output(self, c: int) -> None:
        self.__output.append(c)

    @property
    def string(self) -> str:
        return ''.join(chr(c) for c in self.__output)


# Any object with input() and ready() methods works as a console
# reader.  input() returns the next character code, or None to stop
# the machine; ready() reports console status -- whether a key is
# waiting, which CP/M polls during output as well as input.
class ConsoleReader(typing.Protocol):
    def input(self) -> int | None:
        ...

    def ready(self) -> bool:
        ...


# Any object with an output() method works as a console writer.
# output() is given the next character code to display.
class ConsoleWriter(typing.Protocol):
    def output(self, c: int) -> None:
        ...


# Holds the terminal in raw mode for a whole interactive session,
# so control keys -- Ctrl+C above all -- reach CP/M as ordinary
# characters to read rather than acting on the host, and the
# terminal leaves the echoing to CP/M's own console handling.  The
# cursor is shown again on the way out in case a program left it
# hidden (see DisplayDevice).  Does nothing without an interactive
# terminal.
@contextlib.contextmanager
def _console_session() -> collections.abc.Iterator[None]:
    if sys.platform != 'win32' and sys.stdin.isatty():
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield
        finally:
            sys.stdout.write('\x1b[?25h')       # ensure cursor shown
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    else:
        yield
