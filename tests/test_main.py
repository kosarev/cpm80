import pytest

import cpm80


def test_commands(capsys: pytest.CaptureFixture[str]) -> None:
    cpm80.main(['--temp-disk', 'dir'])
    assert capsys.readouterr().out == '\r\nA>dir\r\r\nNO FILE\r\nA>'
