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


@pytest.fixture(autouse=True)
def _isolated_data_dir(monkeypatch: pytest.MonkeyPatch,
                       tmp_path: pathlib.Path) -> None:
    # Keep the home disk out of the real user data directory.
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / '.data'))


def test_commands(capsys: pytest.CaptureFixture[str],
                  monkeypatch: pytest.MonkeyPatch,
                  tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    cpm80.main(['dir'])
    SIGNON = '62k CP/M vers 2.2\r\n'
    assert capsys.readouterr().out == (SIGNON + '\r\nA>dir\r\r\n'
                                       'A: PIP      COM\r\nA>')


def test_copying_with_pip(capsys: pytest.CaptureFixture[str],
                          monkeypatch: pytest.MonkeyPatch,
                          tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'hello.txt').write_bytes(b'hello from the host\x1a')

    # A: is the home disk (with PIP); --mount . puts the host on B:.
    cpm80.main(['--mount', '.', 'pip a:=b:hello.txt', 'type hello.txt'])

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

    # --no-automount frees A: for the mounted image; --r1715 gives it
    # the R1715 format.
    cpm80.main(['--r1715', '--no-automount', '--mount', str(image), 'dir'])
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
    cpm80.main(['--no-automount', 'dir b:'])
    assert 'Bdos Err On B' in capsys.readouterr().out

    # --mount <dir> mirrors it onto the next drive, B:.
    cpm80.main(['--mount', 'sub', 'dir b:'])
    assert 'B: HELLO    TXT' in capsys.readouterr().out


def test_speed_option(capsys: pytest.CaptureFixture[str],
                      monkeypatch: pytest.MonkeyPatch,
                      tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)

    cpm80.main(['--speed', '4', 'dir'])
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

    cpm80.main(['--mount', '.', 'dir b:'])

    out, err = capsys.readouterr()
    assert 'B: HELLO    TXT' in out
    assert 'not a cpm name' in err


def test_home_disk_not_mirrored(capsys: pytest.CaptureFixture[str],
                                monkeypatch: pytest.MonkeyPatch,
                                tmp_path: pathlib.Path) -> None:
    # Put the data directory inside the mounted directory, so the
    # home disk would be mirrored were it not excluded.
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    (tmp_path / 'cpm80').mkdir()
    monkeypatch.chdir(tmp_path / 'cpm80')

    cpm80.main(['--mount', '.', 'dir b:'])      # Creates disk.img.
    cpm80.main(['--mount', '.', 'dir b:'])      # Would mirror it.

    out, err = capsys.readouterr()
    assert 'no space left' not in err
    assert 'B: DISK     IMG' not in out


def test_files_saved_on_a_mounted_directory_land_on_the_host(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    cpm80.main(['--mount', '.', 'save 1 b:x.dat'])
    assert (tmp_path / 'X.DAT').stat().st_size == 256
