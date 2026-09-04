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
    SIGNON = '62k CP/M vers 2.2\r\n'
    assert capsys.readouterr().out == (SIGNON + '\r\nA>dir\r\r\n'
                                       'A: PIP      COM\r\nA>')


def test_copying_with_pip(capsys: pytest.CaptureFixture[str],
                          monkeypatch: pytest.MonkeyPatch,
                          tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'hello.txt').write_bytes(b'hello from the host\x1a')

    cpm80.main(['--temp-disk', 'pip a:=b:hello.txt',
                'type hello.txt'])

    assert 'hello from the host' in capsys.readouterr().out


def test_speed_option(capsys: pytest.CaptureFixture[str],
                      monkeypatch: pytest.MonkeyPatch,
                      tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)

    # A valid speed runs the usual commands.
    cpm80.main(['--temp-disk', '--speed', '4', 'dir'])
    assert 'PIP' in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cpm80.main(['--speed', 'fast'])
    with pytest.raises(SystemExit):
        cpm80.main(['--speed'])


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


def test_disk_image_not_mirrored_from_data_dir(
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    # Run from the data directory itself, so the persistent disk
    # image sits in the mirrored directory.
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    data_dir = tmp_path / 'cpm80'
    data_dir.mkdir()
    monkeypatch.chdir(data_dir)

    cpm80.main(['dir b:'])          # Creates disk.img.
    cpm80.main(['dir b:'])          # Would mirror it if not excluded.

    out, err = capsys.readouterr()
    assert 'no space left' not in err
    assert 'B: DISK     IMG' not in out


def test_files_saved_on_b_land_on_the_host(
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    cpm80.main(['--temp-disk', 'save 1 b:x.dat'])
    assert (tmp_path / 'X.DAT').stat().st_size == 256
