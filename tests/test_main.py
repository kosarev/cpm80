#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pathlib

import pytest

import cpm80


def test_commands(capsys: pytest.CaptureFixture[str],
                  monkeypatch: pytest.MonkeyPatch,
                  tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    cpm80.main(['--temp-disk', 'dir'])
    assert capsys.readouterr().out == ('\r\nA>dir\r\r\n'
                                       'A: PIP      COM\r\nA>')


def test_copying_with_pip(capsys: pytest.CaptureFixture[str],
                          monkeypatch: pytest.MonkeyPatch,
                          tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'hello.txt').write_bytes(b'hello from the host\x1a')

    cpm80.main(['--temp-disk', 'pip a:=b:hello.txt',
                'type hello.txt'])

    assert 'hello from the host' in capsys.readouterr().out


def test_current_directory_mounts_as_b(
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'hello.txt').write_bytes(b'hello')
    (tmp_path / 'not a cpm name').write_bytes(b'x')

    cpm80.main(['--temp-disk', 'dir b:'])

    out, err = capsys.readouterr()
    assert 'B: HELLO    TXT' in out
    assert 'not a cpm name' in err


def test_files_saved_on_b_land_on_the_host(
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    cpm80.main(['--temp-disk', 'save 1 b:x.dat'])
    assert (tmp_path / 'x.dat').stat().st_size == 256
