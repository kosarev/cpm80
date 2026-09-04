#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80


def test_basic() -> None:
    k = cpm80.StringKeyboard('user 0', 'dir', 'type a.txt')

    input = ''
    while True:
        c = k.input()
        if c is None:
            break

        input += chr(c)

    assert input == 'user 0\ndir\ntype a.txt\n'


def test_never_ready() -> None:
    # Commands are delivered on demand, not typed ahead, so the
    # keyboard never reports a key waiting.
    k = cpm80.StringKeyboard('dir')
    assert k.ready() is False
    k.input()
    assert k.ready() is False
