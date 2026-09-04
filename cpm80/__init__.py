#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import collections.abc
import pathlib
import sys

import platformdirs

from ._console import ADM3ATerminal as ADM3ATerminal
from ._console import ConsoleReader as ConsoleReader
from ._console import ConsoleWriter as ConsoleWriter
from ._console import DisplayDevice as DisplayDevice
from ._console import KeyboardDevice as KeyboardDevice
from ._console import StringDisplay as StringDisplay
from ._console import StringKeyboard as StringKeyboard
from ._console import Terminal as Terminal
from ._console import _console_session
from ._cpm import CPMMachineMixin as CPMMachineMixin
from ._cpm import I8080CPMMachine as I8080CPMMachine
from ._cpm import Z80CPMMachine as Z80CPMMachine
from ._cpm import _load_data
from ._disk import DISK_FORMATS as DISK_FORMATS
from ._disk import SECTOR_SIZE as SECTOR_SIZE
from ._disk import DiskDrive as DiskDrive
from ._disk import DiskFormat as DiskFormat
from ._disk import DiskImage as DiskImage
from ._error import Error as Error
from ._filesystem import FileSystem as FileSystem


# A drive mirroring a host directory.  Mounting takes a snapshot:
# the directory's files land on a fresh in-memory disk under their
# 8.3 names, as many as fit.  Files left out are reported in
# 'warnings', and 'host_paths' tells which host file each CP/M
# name came from.
#
# From then on the mirror maintains itself.  Whenever a program
# closes, deletes, creates or renames a file on the drive, the
# files that changed are written back to the host directory.  A
# warm boot -- the Ctrl+C at the prompt with which CP/M users
# signal a changed disk -- writes the changes back and then
# re-takes the snapshot, picking up what changed on the host side.
# Writing back only creates and updates host files, never deletes
# them, so deleting a file on the drive leaves its host original
# alone.
class HostDrive(DiskDrive):
    __NAME_CHARS = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                             '0123456789#$%&()-_@!')

    def __init__(self, directory: str | pathlib.Path = '.', *,
                 format: DiskFormat | None = None,
                 exclude: collections.abc.Iterable[
                     str | pathlib.Path] = ()) -> None:
        if format is None:
            format = DISK_FORMATS['host']

        self.directory = pathlib.Path(directory)

        # Host files not to mirror, given as paths -- the emulator's
        # own disk image when it happens to sit in this directory.
        self.__excluded = {pathlib.Path(p).resolve() for p in exclude}

        super().__init__(DiskImage(format))
        self.remount()

    # Keep the host directory up to date without explicit flushes:
    # written files appear as CP/M commits them, and a warm boot,
    # the disk-change gesture, flushes and re-takes the snapshot.
    def on_file_commit(self) -> None:
        self.flush_files()

    def on_warm_boot(self) -> None:
        self.flush_files()
        self.remount()

    # Only names already valid in CP/M mount, case aside; anything
    # else is skipped rather than renamed.
    def __make_cpm_name(self, host_name: str) -> str | None:
        name, dot, ext = host_name.partition('.')
        name = name.upper()
        ext = ext.upper()

        if not 1 <= len(name) <= 8:
            return None
        if dot and not 1 <= len(ext) <= 3:
            return None
        if not all(c in self.__NAME_CHARS for c in name + ext):
            return None

        return f'{name}.{ext}' if ext else name

    def remount(self) -> None:
        if not self.directory.is_dir():
            raise Error(f'cannot mount {self.directory}: '
                        'not a directory')

        # Build on a fresh image through its own file system, so
        # the host drive's reactions to writes and boots do not
        # trigger while mounting.
        fs = FileSystem(DiskImage(self.format))
        host_paths: dict[str, pathlib.Path] = {}
        warnings: list[str] = []

        for path in sorted(self.directory.iterdir()):
            if not path.is_file() or path.name.startswith('.'):
                continue

            if path.resolve() in self.__excluded:
                continue

            name = self.__make_cpm_name(path.name)
            if name is None:
                warnings.append(
                    f'{path.name}: not a valid CP/M filename')
                continue

            if name in host_paths:
                taken_by = host_paths[name].name
                warnings.append(
                    f'{path.name}: the name {name} is already '
                    f'taken by {taken_by}')
                continue

            try:
                fs.write(name, path.read_bytes())
            except Error:
                warnings.append(f'{path.name}: no space left')
                continue

            host_paths[name] = path

        self.image = fs.image
        self.host_paths = host_paths
        self.warnings = warnings

    # The host copy may hold the original, unpadded content the
    # padded image content came from.
    @staticmethod
    def __same_as_host_file(path: pathlib.Path, content: bytes) -> bool:
        try:
            existing = path.read_bytes()
        except OSError:
            return False

        padding = b'\x1a' * (-len(existing) % SECTOR_SIZE)
        return content in (existing, existing + padding)

    # Writes the files of the mounted disk back to the host
    # directory -- created and changed files only; never deletes
    # host files.  Contents are written as they are on the disk,
    # record-padded.  Reading the live image through a file system
    # of its own is safe: it only reads.
    def flush_files(self) -> None:
        fs = FileSystem(self.image)
        for cpm_name in fs.names():
            content = fs.read(cpm_name)

            path = self.host_paths.get(cpm_name)
            if path is None:
                path = self.directory / cpm_name

            if self.__same_as_host_file(path, content):
                continue

            path.write_bytes(content)
            self.host_paths[cpm_name] = path


def main(commands: list[str] | None = None) -> None:
    if commands is None:
        commands = sys.argv[1:]

    # TODO: Provide this functionality via a command.
    if commands and commands[0] in ('--help', '-h'):
        sys.exit(
            'CP/M-80 2.2 emulator.\n'
            'usage: cpm80 [--help] [--no-automount] [--speed MHZ] '
            '[--r1715] [--mount TARGET]... [COMMAND...]\n'
            '\n'
            'Options:\n'
            '  --no-automount Do not put the persistent home disk on\n'
            '                 A:; the first --mount takes it instead.\n'
            '  --speed MHZ    Pace the CPU to MHZ million ticks a\n'
            '                 second (the default runs it flat out).\n'
            '  --r1715        Emulate a Robotron 1715 (its own home\n'
            '                 disk and disk format).\n'
            '  --mount TARGET Add a drive: a directory is mirrored,\n'
            '                 a file is mounted as a disk image.\n'
            '                 Repeatable; drives follow in order.\n'
            '\n'
            'COMMAND is a CP/M or internal emulator command to execute\n'
            'automatically before taking input from console.\n'
            '\n'
            'Internal commands:\n'
            '  exit           Terminate emulation and quit.')

    # TODO: Provide this functionality via a command.
    no_automount = False
    speed_mhz = None
    mounts = []
    machine = 'cpm80'
    while commands and commands[0].startswith('--'):
        option = commands.pop(0)
        if option == '--no-automount':
            no_automount = True
        elif option == '--speed':
            if not commands:
                sys.exit('cpm80: --speed needs a value')
            value = commands.pop(0)
            try:
                speed_mhz = float(value)
            except ValueError:
                sys.exit(f'cpm80: invalid speed {value!r}')
        elif option == '--mount':
            if not commands:
                sys.exit('cpm80: --mount needs a directory or image')
            mounts.append(pathlib.Path(commands.pop(0)))
        elif option == '--r1715':
            machine = 'r1715'
        else:
            sys.exit(f'cpm80: unknown option {option!r}')

    console_reader = None
    if commands:
        console_reader = StringKeyboard(*commands)

    # The default machine is the generic 8080 CP/M; the Robotron 1715
    # lives in its own module, imported only when asked for.
    machine_class: type[CPMMachineMixin] = I8080CPMMachine
    if machine == 'r1715':
        from ._r1715 import R1715Machine
        machine_class = R1715Machine

    app_dirs = platformdirs.AppDirs('cpm80')
    data_dir = pathlib.Path(app_dirs.user_data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    disk_path = data_dir / f'{machine}.img'
    machine_format = machine_class.disk_format

    # A cpm80-written image carries its own format; a foreign one
    # takes the machine's.
    def format_of(data: bytes) -> DiskFormat:
        if DiskImage.has_header(data):
            return DiskFormat(**DiskImage.parse_header(data))
        return machine_format

    try:
        drives: list[DiskDrive] = []
        host_drives: list[HostDrive] = []
        persist_image = None
        seed_pip = False

        # The machine's home disk goes on A: unless suppressed.
        if not no_automount:
            disk_data = None
            try:
                disk_data = disk_path.read_bytes()
            except FileNotFoundError:
                pass
            fmt = machine_format if disk_data is None else format_of(disk_data)
            home = DiskImage(fmt, data=disk_data)
            drives.append(DiskDrive(home))
            persist_image = home
            seed_pip = disk_data is None

        # Each --mount is a directory (mirrored) or an image file.
        # Images and the home disk are kept out of a mirrored
        # directory.
        exclude = [disk_path] + [m for m in mounts if m.is_file()]
        for target in mounts:
            if target.is_dir():
                host = HostDrive(target, exclude=exclude)
                host_drives.append(host)
                drives.append(host)
            elif target.is_file():
                data = target.read_bytes()
                drives.append(DiskDrive(
                    DiskImage(format_of(data), data=data, store_format=False)))
            else:
                sys.exit(f'cpm80: no such directory or image: {target}')

        # With no home disk and nothing mounted, A: is a fresh disk
        # to fill; give it PIP too.
        if not drives:
            drives.append(DiskDrive(DiskImage(machine_format)))
            seed_pip = True

        for host in host_drives:
            for warning in host.warnings:
                print(f'cpm80: {warning}', file=sys.stderr)

        m = machine_class(drives=drives, console_reader=console_reader,
                          speed_mhz=speed_mhz)

        # A fresh home disk gets PIP, so files copy between drives out
        # of the box.
        if seed_pip:
            m.make_file('pip.com')
            m.write_file(_load_data('pip.com'))
            m.close_file()

        try:
            with _console_session():
                m.run()
        except KeyboardInterrupt:
            # Reached only where the terminal is not in raw mode
            # (so Ctrl+C stays a host interrupt rather than a
            # character): quit rather than show a traceback.
            pass
        finally:
            if persist_image is not None:
                disk_path.write_bytes(persist_image.data)
            for host in host_drives:
                host.flush_files()
    except Error as e:
        sys.exit(f'cpm80: {e}')


if __name__ == '__main__':
    main()
