#!/usr/bin/env python3

import cpm80


def test_basic():
    k = cpm80.StringKeyboard('user 0', 'dir', 'type a.txt')
    input = ''
    while not k.end_of_input:
        input += chr(k.input())
    assert input == 'user 0\ndir\ntype a.txt\n'
