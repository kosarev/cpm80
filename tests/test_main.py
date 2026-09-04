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

    cpm80.main(['--temp-disk', '--mount', '.', 'pip a:=b:hello.txt',
                'type hello.txt'])

    assert 'hello from the host' in capsys.readouterr().out


def test_mounting_an_r1715_image(capsys: pytest.CaptureFixture[str],
                                 monkeypatch: pytest.MonkeyPatch,
                                 tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)

    # Build an image in the Robotron 1715 format and save it.
    fs = cpm80.FileSystem(cpm80.DiskImage(cpm80.DISK_FORMATS['r1715']))
    fs.write('game.com', b'\xc9')      # a RET, harmless
    image = tmp_path / 'disk.cpm'
    image.write_bytes(bytes(fs.image.data))

    # The machine sets the format; --mount supplies the image, which
    # becomes A: since the r1715 machine has no home disk.
    cpm80.main(['--r1715', '--mount', str(image), 'dir'])
    assert 'GAME     COM' in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cpm80.main(['--mount'])                       # missing target
    with pytest.raises(SystemExit):
        cpm80.main(['--r1715', '--mount', str(tmp_path / 'nope.cpm')])


def test_mount_a_directory(capsys: pytest.CaptureFixture[str],
                           monkeypatch: pytest.MonkeyPatch,
                           tmp_path: pathlib.Path) -> None:
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'hello.txt').write_bytes(b'hi')
    monkeypatch.chdir(tmp_path)

    # Without --mount there is no B: drive: selecting it errors.
    cpm80.main(['--temp-disk', 'dir b:'])
    assert 'Bdos Err On B' in capsys.readouterr().out

    # --mount <dir> mirrors it onto the next drive, B:.
    cpm80.main(['--temp-disk', '--mount', 'sub', 'dir b:'])
    assert 'B: HELLO    TXT' in capsys.readouterr().out


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


def test_mounted_directory_warns_of_unmountable_files(
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'hello.txt').write_bytes(b'hello')
    (tmp_path / 'not a cpm name').write_bytes(b'x')

    cpm80.main(['--temp-disk', '--mount', '.', 'dir b:'])

    out, err = capsys.readouterr()
    assert 'B: HELLO    TXT' in out
    assert 'not a cpm name' in err


def test_disk_image_not_mirrored_from_data_dir(
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    # Run from the data directory itself and mount it, so the
    # persistent disk image sits in the mirrored directory.
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    data_dir = tmp_path / 'cpm80'
    data_dir.mkdir()
    monkeypatch.chdir(data_dir)

    cpm80.main(['--mount', '.', 'dir b:'])      # Creates disk.img.
    cpm80.main(['--mount', '.', 'dir b:'])      # Would mirror it.

    out, err = capsys.readouterr()
    assert 'no space left' not in err
    assert 'B: DISK     IMG' not in out


def test_files_saved_on_a_mounted_directory_land_on_the_host(
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    cpm80.main(['--temp-disk', '--mount', '.', 'save 1 b:x.dat'])
    assert (tmp_path / 'X.DAT').stat().st_size == 256
