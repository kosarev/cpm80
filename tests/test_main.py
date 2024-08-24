#!/usr/bin/env python3

import cpm80


def test_main(capsys):
    cpm80.main(['--temp-disk', '-c', 'dir'])
    assert capsys.readouterr().out == '\r\nA>dir\r\r\nNO FILE\r\nA>'
