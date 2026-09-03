#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80


def test_basic() -> None:
    d = cpm80.StringDisplay()
    for c in 'user 0\ndir\ntype a.txt\n':
        d.output(ord(c))
    assert d.string == 'user 0\ndir\ntype a.txt\n'
