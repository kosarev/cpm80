#!/usr/bin/env python3

import cpm80


def test_commands(capsys):
    cpm80.main(['--temp-disk', 'dir'])
    assert capsys.readouterr().out == '\r\nA>dir\r\r\nNO FILE\r\nA>'
