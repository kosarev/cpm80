#!/usr/bin/env python3

import cpm80


def test_c_writestr(capsys):
    m = cpm80.I8080CPMMachine()
    m.write_str('abc')
    assert capsys.readouterr().out == 'abc'
