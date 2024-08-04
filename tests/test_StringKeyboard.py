#!/usr/bin/env python3

import cpm80


def test_basic():
    k = cpm80.StringKeyboard('user 0', 'dir', 'type a.txt')

    input = ''
    while True:
        c = k.input()
        if c is None:
            break

        input += chr(c)

    assert input == 'user 0\ndir\ntype a.txt\n'
