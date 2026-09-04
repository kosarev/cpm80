#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import collections.abc
import contextlib
import importlib.resources
import os
import pathlib
import sys
import time
import typing

import platformdirs
import z80

if sys.platform == 'win32':
    import msvcrt
else:
    import select
    import termios
    import tty

SECTOR_SIZE = 128


def _load_data(filename: str) -> bytes:
    files = importlib.resources.files('cpm80')
    return files.joinpath(filename).read_bytes()


class Error(BaseException):
    pass


class DiskFormat:
    # The defaults describe a roomy synthetic disk of nearly the
    # 8M the file system supports.
    def __init__(self, *, sectors_per_track: int = 64,
                 num_reserved_tracks: int = 1, block_size: int = 16384,
                 num_blocks: int = 500,
                 num_dir_entries: int = 512) -> None:
        def _div_ceil(a: int, b: int) -> int:
            return -(a // -b)

        if block_size not in (1024, 2048, 4096, 8192, 16384):
            raise Error(f'invalid block size ({block_size})')

        if block_size == 1024 and num_blocks > 0x100:
            raise Error('block size 1024 is not valid for disks with '
                        'more than 0x100 blocks')

        self.sectors_per_track = sectors_per_track
        self.num_reserved_tracks = num_reserved_tracks
        self.block_size = block_size
        self.num_blocks = num_blocks
        self.num_dir_entries = num_dir_entries

        self.params = {
            'sectors_per_track': sectors_per_track,
            'num_reserved_tracks': num_reserved_tracks,
            'block_size': block_size,
            'num_blocks': num_blocks,
            'num_dir_entries': num_dir_entries}

        # TODO: Support arbitrary skew factors.
        self.skew_factor = 0  # No translation.

        # TODO: Support fixed drives.
        self.removable = True

        self.spec = tuple(f'{p}={v}' for p, v in self.params.items())

        # CP/M Disk Parameter Block Fields.
        self.bls_block_size = self.block_size
        self.spt_sectors_per_track = self.sectors_per_track
        self.bsh_block_shift_factor = self.block_size.bit_length() - 8
        self.blm_allocation_block_mask = 2**self.bsh_block_shift_factor - 1
        self.dsm_disk_size_max = self.num_blocks - 1
        self.exm_extent_mask = (self.blm_allocation_block_mask >> 3
                                if self.dsm_disk_size_max < 0x100
                                else self.blm_allocation_block_mask >> 4)
        self.drm_max_dir_entry = self.num_dir_entries - 1
        self.cks_directory_check_size = (self.num_dir_entries // 4
                                         if self.removable else 0)
        self.off_system_tracks_offset = self.num_reserved_tracks

        DIR_ENTRY_SIZE = 32
        num_dir_blocks = _div_ceil(self.num_dir_entries * DIR_ENTRY_SIZE,
                                   self.block_size)
        dir_alloc_mask = (0xffff >> num_dir_blocks) ^ 0xffff
        self.al0_allocation_mask = (dir_alloc_mask >> 8) & 0xff
        self.al1_allocation_mask = (dir_alloc_mask >> 0) & 0xff

        self.reserved_size = (self.num_reserved_tracks *
                              self.sectors_per_track * SECTOR_SIZE)
        self.unreserved_size = self.num_blocks * self.block_size
        self.disk_size = self.reserved_size + self.unreserved_size

    def __repr__(self) -> str:
        params = ', '.join(f'{p}={v}' for p, v in self.params.items())
        return f'{type(self).__name__}({params})'

    @staticmethod
    def parse_spec(specs: collections.abc.Iterable[str]) -> dict[str, int]:
        params = DiskFormat().params
        for s in specs:
            p, eq, v = s.partition('=')
            if p == '' or eq != '=' or v == '':
                raise Error(f'invalid specifier {s!r}')
            if p not in params:
                raise Error(f'unknown parameter {p!r}')

            try:
                value = int(v)
            except ValueError as e:
                raise Error(f'invalid value for parameter {p!r}: {e}')

            params[p] = value

        return params

    def translate_sector(self, logical_sector: int) -> int:
        assert self.skew_factor == 0
        physical_sector = logical_sector
        return physical_sector


DISK_FORMATS = {
    'default': DiskFormat(),

    # Also used on Orion 128 machines. The number of blocks is
    # one less than it could be, likely due to a mistake, so the
    # last block is never used.
    'korvet': DiskFormat(sectors_per_track=40, num_reserved_tracks=4,
                         block_size=2048, num_blocks=389,
                         num_dir_entries=128),

    # Robotron 1715 SCP3, its 800K floppies (cpmtools calls it
    # 17153): 160 tracks of five 1024-byte sectors, four reserved.
    'r1715': DiskFormat(sectors_per_track=40, num_reserved_tracks=4,
                        block_size=2048, num_blocks=390,
                        num_dir_entries=128),
}

# The name predates the default format becoming this roomy.
DISK_FORMATS['host'] = DISK_FORMATS['default']


# A machine cpm80 can present.  disk_format names (in DISK_FORMATS)
# the format of its home disk and of foreign images mounted on it; a
# cpm80-written image overrides it from its own header.  terminal and
# charset name (in TERMINALS and CHARSETS) the terminal the machine's
# programs draw on and the character set they use.  The home disk is
# named after the machine (cpm80.img, r1715.img).  A CPU will join
# here.
class MachineType:
    def __init__(self, *, disk_format: str = 'default',
                 terminal: str = 'adm3a', charset: str = 'ascii') -> None:
        self.__disk_format = disk_format
        self.__terminal = terminal
        self.__charset = charset

    @property
    def disk_format(self) -> DiskFormat:
        return DISK_FORMATS[self.__disk_format]

    # A fresh terminal built with the machine's character set.
    def make_terminal(self) -> 'Terminal':
        return TERMINALS[self.__terminal](CHARSETS[self.__charset])

    def __repr__(self) -> str:
        return (f'{type(self).__name__}(disk_format={self.__disk_format!r}, '
                f'terminal={self.__terminal!r}, charset={self.__charset!r})')


MACHINES = {
    'cpm80': MachineType(),
    'r1715': MachineType(disk_format='r1715', terminal='r1715',
                         charset='r1715'),
}


class DiskImage:
    __SIGNATURE = 'cpm80 disk image <https://pypi.org/project/cpm80>'

    def __init__(self, format: DiskFormat, *,
                 data: bytes | bytearray | None = None,
                 store_format: bool = True) -> None:
        self.format = format

        size = format.disk_size
        self.data = bytearray(size)
        self.data[:] = b'\xe5' * size

        if data is not None:
            # Slice assignment on a bytearray resizes it, so a
            # mismatch would otherwise pass silently.
            if len(data) != size:
                raise Error(f'invalid disk image size ({len(data)}, '
                            f'expected {size})')
            self.data[:] = data

        if store_format:
            spec = ' '.join(self.format.spec)
            header = f'{self.__SIGNATURE}\n{spec}\n\n'.encode('ascii')

            if self.format.reserved_size < len(header):
                raise Error('no reserved space for disk format')

            self.data[:len(header)] = header

    @staticmethod
    def has_header(data: bytes) -> bool:
        # True for an image cpm80 wrote, which carries its own format.
        return data.startswith(DiskImage.__SIGNATURE.encode('ascii'))

    @staticmethod
    def parse_header(data: bytes) -> dict[str, int]:
        if not DiskImage.has_header(data):
            raise Error('no disk signature')

        try:
            header = data.partition(b'\n\n')[0].decode('ascii').splitlines()
        except UnicodeDecodeError as e:
            raise Error(f'cannot decode disk header: {e}')

        # Drop the signature line.
        header.pop(0)

        if not header:
            raise Error('no disk parameters')
        format = DiskFormat.parse_spec(header.pop(0).split())

        if header:
            raise Error(f'unexpected header line {header[0]!r}')

        return format

    def get_sector(self, sector: int, track: int) -> memoryview:
        # An out-of-range sector would otherwise silently alias
        # into another track.
        if not 0 <= sector < self.format.spt_sectors_per_track:
            raise Error(f'invalid sector number ({sector})')

        sector_index = sector + track * self.format.spt_sectors_per_track
        offset = sector_index * SECTOR_SIZE
        if track < 0 or offset + SECTOR_SIZE > len(self.data):
            raise Error(f'invalid track number ({track})')

        return memoryview(self.data)[offset:offset + SECTOR_SIZE]

    def translate_sector(self, logical_sector: int) -> int:
        return self.format.translate_sector(logical_sector)


class DiskDrive:
    def __init__(self, image: DiskImage | None = None) -> None:
        if image is None:
            image = DiskImage(DiskFormat())

        self.image = image
        self.current_sector = 0
        self.current_track = 0

    @property
    def format(self) -> DiskFormat:
        return self.image.format

    def translate_sector(self, logical_sector: int) -> int:
        return self.image.translate_sector(logical_sector)

    def read_sector(self) -> bytes:
        sector = self.image.get_sector(self.current_sector, self.current_track)
        return bytes(sector)

    def write_sector(self, data: bytes | bytearray | memoryview) -> None:
        assert len(data) == SECTOR_SIZE
        sector = self.image.get_sector(self.current_sector, self.current_track)
        sector[:] = data

    # Called after a BDOS call that closed, deleted, created or
    # renamed a file on the drive has completed.
    def on_file_commit(self) -> None:
        pass

    # Called on warm boots, when CP/M re-logs its disks.
    def on_warm_boot(self) -> None:
        pass


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


class KeyboardDevice:
    def __init__(self) -> None:
        self.__ctrl_c_count = 0

    def input(self) -> int | None:
        # The terminal is put in raw mode for the whole session (see
        # _console_session), so a key is read straight from the file
        # descriptor -- matching the descriptor-level ready() check,
        # and without the mode change that would discard it.
        if sys.platform == 'win32':
            # Note that Ctrl+C comes as an ordinary character and
            # special keys come as two reads with a 0x00 or 0xe0
            # prefix, undecoded, just as escape sequences on Unix.
            ch = ord(msvcrt.getch())
        else:
            data = os.read(sys.stdin.fileno(), 1)
            if not data:
                return None     # end of input
            ch = data[0]

        # Catch Ctrl+C.
        if ch == 3:
            self.__ctrl_c_count += 1
            if self.__ctrl_c_count >= 3:
                return None
        else:
            self.__ctrl_c_count = 0

        # Translate backspace.
        if ch == 127:
            ch = 8

        return ch

    def ready(self) -> bool:
        # Only an interactive terminal has keys waiting; a
        # redirected or captured stdin never does, and polling it
        # would misreport its end as a waiting character.
        try:
            if not sys.stdin.isatty():
                return False
        except (OSError, ValueError):
            return False

        if sys.platform == 'win32':
            return msvcrt.kbhit()
        else:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            return bool(readable)


class StringKeyboard:
    def __init__(self, *commands: str) -> None:
        self.__input = '\n'.join(commands) + '\n'
        self.__i = 0

    def input(self) -> int | None:
        if self.__i >= len(self.__input):
            return None

        c = self.__input[self.__i]
        self.__i += 1
        return ord(c)

    # Never reports a key waiting: the commands are delivered one at
    # a time only when the machine reads, never typed ahead.  A
    # reader that reported ready while commands remain would have
    # them consumed by CP/M's console-status polling during output.
    def ready(self) -> bool:
        return False


# A character set maps a byte to the glyph a machine shows for it.
# The default is ASCII, where a byte shows its own character.  A
# machine with its own character generator (the R1715) has its own
# set.
class Charset:
    def __init__(self, mapping: dict[int, str]) -> None:
        self.__mapping = mapping

    def translate(self, c: int) -> str:
        return self.__mapping.get(c, chr(c))


# The Robotron 1715 glyphs that differ from ASCII: capital Cyrillic
# where ASCII has the lower-case letters and the symbols after them
# (the KOI-7 N2 layout, GOST 13052), and a solid block at 0xff that
# its games fill the screen with.
_R1715_GLYPHS = {
    0x60: 'Ю', 0x61: 'А', 0x62: 'Б', 0x63: 'Ц', 0x64: 'Д', 0x65: 'Е',
    0x66: 'Ф', 0x67: 'Г', 0x68: 'Х', 0x69: 'И', 0x6a: 'Й', 0x6b: 'К',
    0x6c: 'Л', 0x6d: 'М', 0x6e: 'Н', 0x6f: 'О', 0x70: 'П', 0x71: 'Я',
    0x72: 'Р', 0x73: 'С', 0x74: 'Т', 0x75: 'У', 0x76: 'Ж', 0x77: 'В',
    0x78: 'Ь', 0x79: 'Ы', 0x7a: 'З', 0x7b: 'Ш', 0x7c: 'Э', 0x7d: 'Щ',
    0x7e: 'Ч', 0x7f: 'Ъ',
    0xff: '█',
}

# The character sets a machine can select (see MACHINES).
CHARSETS = {
    'ascii': Charset({}),
    'r1715': Charset(_R1715_GLYPHS),
}


# Translates the control codes a CP/M program emits for its terminal
# into ANSI for the host terminal.  A machine selects which terminal
# it emulates.  translate() returns the display text for one output
# byte: its character through the terminal's character set, or the
# ANSI for a control code.  After a byte that moves or clears the
# cursor it sets draws_screen, so the display can hide the blinking
# hardware cursor while a program paints the screen.
class Terminal(typing.Protocol):
    draws_screen: bool

    def translate(self, c: int) -> str:
        ...


# The ADM-3A, the terminal the bundled CP/M expects.
class ADM3ATerminal:
    # Waiting for the rest of an escape sequence: 0 none, 1 seen
    # ESC, 2 want the row byte, 3 want the column byte.
    def __init__(self, charset: Charset | None = None) -> None:
        self.__charset = charset if charset is not None else Charset({})
        self.__pending = 0
        self.__row = 0
        self.draws_screen = False

    def translate(self, c: int) -> str:
        self.draws_screen = False

        if self.__pending == 1:
            if c == ord('='):       # ESC= loads the cursor position
                self.__pending = 2
                return ''
            # some other escape; pass it on
            self.__pending = 0
            return '\x1b' + chr(c)

        if self.__pending == 2:
            self.__row = c
            self.__pending = 3
            return ''

        if self.__pending == 3:
            # The row and column are biased by a space; ANSI counts
            # from one.
            row = max(0, self.__row - 0x20) + 1
            col = max(0, c - 0x20) + 1
            self.__pending = 0
            self.draws_screen = True
            return f'\x1b[{row};{col}H'

        SEQUENCES = {
            0x0b: '\x1b[A',         # cursor up
            0x0c: '\x1b[C',         # cursor right
            0x1a: '\x1b[2J\x1b[H',  # clear screen and home
            0x1e: '\x1b[H',         # home
        }
        if c == 0x1b:               # ESC
            self.__pending = 1
            return ''
        if c in SEQUENCES:
            self.draws_screen = True
            return SEQUENCES[c]
        return self.__charset.translate(c)


# The Robotron 1715 terminal.  Its cursor addressing is ESC followed
# by a row byte and a column byte, each biased by 0x80.  Form feed
# clears the screen.  Its games draw the screen as a plain run of
# characters and rely on the terminal to wrap to the next line at the
# right edge, so this tracks the cursor column and wraps at the
# screen width.  This covers what the R1715 games observed emit; their
# Cyrillic text is handled by the character set.
class R1715Terminal:
    __WIDTH = 80

    # Waiting for the rest of a sequence: 0 none, 1 want the row byte,
    # 2 want the column byte.
    def __init__(self, charset: Charset | None = None) -> None:
        self.__charset = charset if charset is not None else Charset({})
        self.__pending = 0
        self.__row = 0
        self.__col = 0
        self.draws_screen = False

    def translate(self, c: int) -> str:
        self.draws_screen = False

        if self.__pending == 1:
            self.__row = c
            self.__pending = 2
            return ''

        if self.__pending == 2:
            # The row and column are biased by 0x80; ANSI counts from
            # one.
            row = max(0, self.__row - 0x80) + 1
            col = max(0, c - 0x80) + 1
            self.__pending = 0
            self.__col = col - 1
            self.draws_screen = True
            return f'\x1b[{row};{col}H'

        if c == 0x1b:               # ESC introduces a cursor position
            self.__pending = 1
            return ''
        if c == 0x0c:               # form feed clears the screen
            self.__col = 0
            self.draws_screen = True
            return '\x1b[2J\x1b[H'
        if c == 0x0d:               # carriage return
            self.__col = 0
            return '\r'
        if c < 0x20:                # other controls do not move the column
            return self.__charset.translate(c)

        # A printable character.  Wrap to the next line before it if
        # the row is full.
        prefix = ''
        if self.__col >= self.__WIDTH:
            prefix = '\r\n'
            self.__col = 0
        self.__col += 1
        return prefix + self.__charset.translate(c)


# The terminals a machine can select (see MACHINES).  Each is built
# with the machine's character set.
TERMINALS: dict[str, collections.abc.Callable[[Charset], Terminal]] = {
    'adm3a': ADM3ATerminal,
    'r1715': R1715Terminal,
}


# Writes a terminal's output to the host tty and manages the hardware
# cursor.  The translation itself is the terminal's; this is the sink.
class DisplayDevice:
    def __init__(self, terminal: Terminal | None = None) -> None:
        self.__terminal = terminal if terminal is not None else ADM3ATerminal()
        self.__cursor_hidden = False

    def __write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    # A program that positions the cursor is drawing a screen; hide
    # the hardware cursor so it does not blink chasing the writes.
    # show_cursor() brings it back when control returns to CCP (see
    # on_wboot) and when the session ends.
    def __hide_cursor(self) -> None:
        if not self.__cursor_hidden:
            self.__write('\x1b[?25l')
            self.__cursor_hidden = True

    def show_cursor(self) -> None:
        if self.__cursor_hidden:
            self.__write('\x1b[?25h')
            self.__cursor_hidden = False

    def output(self, c: int) -> None:
        text = self.__terminal.translate(c)
        if self.__terminal.draws_screen:
            self.__hide_cursor()
        if text:
            self.__write(text)


class StringDisplay:
    def __init__(self) -> None:
        self.__output: list[int] = []

    def output(self, c: int) -> None:
        self.__output.append(c)

    @property
    def string(self) -> str:
        return ''.join(chr(c) for c in self.__output)


# Any object with input() and ready() methods works as a console
# reader.  input() returns the next character code, or None to stop
# the machine; ready() reports console status -- whether a key is
# waiting, which CP/M polls during output as well as input.
class ConsoleReader(typing.Protocol):
    def input(self) -> int | None:
        ...

    def ready(self) -> bool:
        ...


# Any object with an output() method works as a console writer.
# output() is given the next character code to display.
class ConsoleWriter(typing.Protocol):
    def output(self, c: int) -> None:
        ...


# The mixin expects to be combined with a z80 machine class.
# This declares that to the type checker without imposing a runtime base.
if typing.TYPE_CHECKING:
    _MachineBase = z80.I8080Machine
else:
    _MachineBase = object


class CPMMachineMixin(_MachineBase):
    __REBOOT = 0x0000
    __CURRENT_DISK_ADDR = 0x0004
    __DEFAULT_FCB = 0x005c
    __TPA = 0x0100

    BDOS_ENTRY = 0x0005
    C_WRITESTR = 9
    C_STAT = 0xb
    S_BDOSVER = 0xc
    F_OPEN = 0xf
    F_CLOSE = 0x10
    F_SFIRST = 0x11
    F_SNEXT = 0x12
    F_DELETE = 0x13
    F_READ = 0x14
    F_WRITE = 0x15
    F_MAKE = 0x16
    F_RENAME = 0x17
    F_DMAOFF = 0x1a

    # The CP/M system is relocated to a 62K configuration: CCP at
    # 0xD000, BDOS at 0xD800, so the BIOS follows at 0xE600 and the
    # TPA runs 0x0100-0xD000, about 53K -- enough for large
    # programs.
    __BDOS_BASE = 0xd800
    __BDOS_CODE_ENTRY = __BDOS_BASE + 0x11

    __CCP_BASE = 0xd000
    __CCP_READ_COMMAND = __CCP_BASE + 0x1aa
    __CCP_GET_COMMAND = __CCP_BASE + 0x385
    __CCP_RUN_COMMAND = __CCP_BASE + 0x398

    __BIOS_BASE = 0xe600

    # One RET per drive, right after the BIOS vectors: a
    # file-committing BDOS call returns through the RET of the
    # drive it works on, so its completion notifies that drive.
    __COMMIT_RETURNS_BASE = __BIOS_BASE + 0x40

    __BIOS_DISK_TABLES_HEAP_BASE = __BIOS_BASE + 0x80

    # A frame is a short slice of emulated time paced against the
    # wall clock; 50 a second is smooth and cheap.
    __FRAMES_PER_SECOND = 50

    def __init__(self, *,
                 drives: collections.abc.Sequence[DiskDrive] | None = None,
                 console_reader: ConsoleReader | None = None,
                 console_writer: ConsoleWriter | None = None,
                 speed_mhz: float | None = None) -> None:
        # None runs the machine as fast as it can; a speed paces it
        # to that many million ticks a second.
        if speed_mhz is None:
            self.__frame_ticks = 0
        else:
            ticks_per_second = speed_mhz * 1_000_000
            self.__frame_ticks = round(ticks_per_second /
                                       self.__FRAMES_PER_SECOND)

        if drives is None:
            drives = DiskDrive(),

        NUM_DRIVES_MAX = 16
        if not 1 <= len(drives) <= NUM_DRIVES_MAX:
            raise Error(f'1 to {NUM_DRIVES_MAX} drives supported, '
                        f'got {len(drives)}')

        self.__drives = tuple(drives)
        self.__drive = self.__drives[0]
        self.__console_reader = console_reader or KeyboardDevice()
        self.__console_writer = console_writer or DisplayDevice()
        self.__done = False

        self.__breakpoints: dict[
                int, collections.abc.Callable[[], None] | None] = {
            self.__CCP_READ_COMMAND: self.on_read_ccp_command,
            self.__CCP_GET_COMMAND: None,
            self.__CCP_RUN_COMMAND: self.on_ccp_command,
            self.__BDOS_CODE_ENTRY: self.on_bdos_entry,
        }

        for i in range(len(self.__drives)):
            addr = self.__COMMIT_RETURNS_BASE + i
            assert addr not in self.__breakpoints
            self.__breakpoints[addr] = self.__on_commit_return

        BIOS_VECTORS = (
            self.on_boot,
            self.on_wboot,
            self.on_const,
            self.on_conin,
            self.on_conout,
            self.on_list,
            self.on_punch,
            self.on_reader,
            self.on_home,
            self.on_seldsk,
            self.on_settrk,
            self.on_setsec,
            self.on_setdma,
            self.on_read,
            self.on_write,
            self.on_listst,
            self.on_sectran)

        self.__bios_vectors: dict[
            int, collections.abc.Callable[[], None]] = {}
        for i, handler in enumerate(BIOS_VECTORS):
            addr = self.__BIOS_BASE + i * 3

            assert addr not in self.__bios_vectors
            self.__bios_vectors[addr] = handler

            assert addr not in self.__breakpoints
            self.__breakpoints[addr] = handler

        for addr in self.__breakpoints:
            self.set_breakpoint(addr)

        self.__ccp_command_line: str | None = None

        self.on_boot()

    def __allocate_disk_table_block(self, image: bytes) -> int:
        addr = self.__disk_tables_heap
        self.__disk_tables_heap += len(image)
        self.set_memory_block(addr, image)
        return addr

    def __set_up_disk_tables(self) -> None:
        # Shared by all drives.
        dirbuf_scratch_pad = self.__allocate_disk_table_block(b'\x00' * 128)

        tables = []
        for drive in self.__drives:
            f = drive.format

            dpb_disk_param_block = self.__allocate_disk_table_block(
                f.spt_sectors_per_track.to_bytes(2, 'little') +
                f.bsh_block_shift_factor.to_bytes(1, 'little') +
                f.blm_allocation_block_mask.to_bytes(1, 'little') +
                f.exm_extent_mask.to_bytes(1, 'little') +
                f.dsm_disk_size_max.to_bytes(2, 'little') +
                f.drm_max_dir_entry.to_bytes(2, 'little') +
                f.al0_allocation_mask.to_bytes(1, 'little') +
                f.al1_allocation_mask.to_bytes(1, 'little') +
                f.cks_directory_check_size.to_bytes(2, 'little') +
                f.off_system_tracks_offset.to_bytes(2, 'little'))

            xlt_sector_translation_vector = 0x0000
            bdos_scratch_pad1 = 0x0000
            bdos_scratch_pad2 = 0x0000
            bdos_scratch_pad3 = 0x0000
            cks = (f.drm_max_dir_entry + 1) // 4 if f.removable else 0
            csv_scratch_pad = self.__allocate_disk_table_block(b'\x00' * cks)
            alv_scratch_pad = self.__allocate_disk_table_block(
                b'\x00' * (f.dsm_disk_size_max // 8 + 1))

            tables.append(self.__allocate_disk_table_block(
                xlt_sector_translation_vector.to_bytes(2, 'little') +
                bdos_scratch_pad1.to_bytes(2, 'little') +
                bdos_scratch_pad2.to_bytes(2, 'little') +
                bdos_scratch_pad3.to_bytes(2, 'little') +
                dirbuf_scratch_pad.to_bytes(2, 'little') +
                dpb_disk_param_block.to_bytes(2, 'little') +
                csv_scratch_pad.to_bytes(2, 'little') +
                alv_scratch_pad.to_bytes(2, 'little')))

        self.__disk_header_tables = tuple(tables)

    def on_boot(self) -> None:
        for addr in self.__bios_vectors:
            self.set_memory_block(addr, z80.RET().encode())

        for i in range(len(self.__drives)):
            self.set_memory_block(self.__COMMIT_RETURNS_BASE + i,
                                  z80.RET().encode())

        self.__disk_tables_heap = self.__BIOS_DISK_TABLES_HEAP_BASE
        self.__set_up_disk_tables()

        self.sp = 0x100

        CURRENT_DISK = 0
        self.set_memory_block(self.__CURRENT_DISK_ADDR,
                              CURRENT_DISK.to_bytes(1, 'little'))

        # The BIOS signon: a cold boot announces the system, sized
        # by the 62K configuration the system is relocated for.
        MEMORY_SIZE_K = 62
        for c in f'{MEMORY_SIZE_K}k CP/M vers 2.2\r\n':
            self.__console_writer.output(ord(c))

        self.on_wboot()

    def on_wboot(self) -> None:
        # A warm boot restores the parts of the system a transient
        # program may have overwritten -- the CCP and BDOS, and the
        # page-zero jumps that reach them.  A real CP/M reloads CCP
        # and BDOS from disk here for exactly this reason; a program
        # built for a machine with more memory can otherwise write
        # over ours.
        self.set_memory_block(self.__CCP_BASE, _load_data('ccp.bin'))
        self.set_memory_block(self.__BDOS_BASE, _load_data('bdos.bin'))

        # 0x0000 jumps to WBOOT (the address at 0x0001 is also how a
        # program locates the BIOS table); 0x0005 jumps to the BDOS.
        WBOOT = self.__BIOS_BASE + 3
        self.set_memory_block(self.__REBOOT, z80.JP(WBOOT).encode())
        self.set_memory_block(self.BDOS_ENTRY,
                              z80.JP(self.__BDOS_CODE_ENTRY).encode())

        for drive in self.__drives:
            drive.on_warm_boot()

        # Back to CCP: a screen program that hid the cursor has
        # ended, so the prompt gets it back.
        show_cursor = getattr(self.__console_writer, 'show_cursor', None)
        if show_cursor is not None:
            show_cursor()

        DEFAULT_DMA = 0x80
        self.__dma = DEFAULT_DMA

        # CCP takes the disk to use in C.
        self.c = self.memory[self.__CURRENT_DISK_ADDR]

        self.pc = self.__CCP_BASE

    def on_const(self) -> None:
        # The BIOS reports console status as a whole byte: all ones
        # for ready, all zeros for not.
        self.a = 0xff if self.__console_reader.ready() else 0

    def on_conin(self) -> None:
        c = self.__console_reader.input()
        if c is None:
            self.__done = True
            return

        self.a = c

    def on_conout(self) -> None:
        self.__console_writer.output(self.c)

    def on_list(self) -> None:
        assert 0  # TODO

    def on_punch(self) -> None:
        assert 0  # TODO

    def on_reader(self) -> None:
        assert 0  # TODO

    def on_home(self) -> None:
        self.__drive.current_track = 0

    def on_seldsk(self) -> None:
        disk = self.c
        if disk >= len(self.__drives):
            self.hl = 0  # No such disk.
            return

        self.__drive = self.__drives[disk]
        self.hl = self.__disk_header_tables[disk]

    def on_settrk(self) -> None:
        self.__drive.current_track = self.bc

    def on_setsec(self) -> None:
        self.__drive.current_sector = self.bc

    def on_setdma(self) -> None:
        self.__dma = self.bc

    def on_read(self) -> None:
        try:
            data = self.__drive.read_sector()
        except Error:
            self.a = 1  # Read error.
            return

        self.set_memory_block(self.__dma, data)
        self.a = 0  # Read OK.

    def on_write(self) -> None:
        data = self.memory[self.__dma:self.__dma + SECTOR_SIZE]
        try:
            self.__drive.write_sector(data)
        except Error:
            self.a = 1  # Write error.
            return

        self.a = 0  # Write OK.

    def on_listst(self) -> None:
        assert 0  # TODO

    def on_sectran(self) -> None:
        self.hl = self.__drive.translate_sector(self.bc)

    # How drives learn that their files changed: every BDOS call
    # enters through the single BDOS code entry, where a breakpoint
    # shows us the function about to run.  For the functions that
    # change what files a drive holds -- close, delete, make,
    # rename -- the drive must be notified after the work is done,
    # not at the entry, so the notification is arranged to happen
    # on return: an extra return
    # address is pushed on top of the caller's, addressing the RET
    # belonging to the drive the call works on.  When BDOS finishes
    # and returns, it first lands on that RET, whose breakpoint
    # notifies the drive, and the RET itself then pops the caller's
    # address and resumes it as if nothing happened.  The stack
    # carries all the state: which drive to notify and where to
    # continue.
    def on_bdos_entry(self) -> None:
        if self.c not in (self.F_CLOSE, self.F_DELETE, self.F_MAKE,
                          self.F_RENAME):
            return

        DEFAULT_DRIVE = 0
        fcb_drive = self.memory[self.de]
        if fcb_drive == DEFAULT_DRIVE:
            disk = self.memory[self.__CURRENT_DISK_ADDR] & 0xf
        else:
            disk = fcb_drive - 1

        if disk < len(self.__drives):
            self.__push(self.__COMMIT_RETURNS_BASE + disk)

    def __on_commit_return(self) -> None:
        disk = self.pc - self.__COMMIT_RETURNS_BASE
        self.__drives[disk].on_file_commit()

    def on_breakpoint(self) -> None:
        handler = self.__breakpoints.get(self.pc)
        if handler:
            handler()

    # TODO: Should be implemented in the CPU package.
    def __push(self, nn: int) -> None:
        memory = self.memory
        assert isinstance(memory, memoryview)
        self.sp = (self.sp - 1) & 0xffff
        memory[self.sp] = (nn >> 8) & 0xff
        self.sp = (self.sp - 1) & 0xffff
        memory[self.sp] = (nn >> 0) & 0xff

    # Runs until the next breakpoint is handled, or, when told to
    # park at an address, until execution is about to hit it, which
    # is reported by returning False.  Breakpoints catch before the
    # marked instruction executes, so handled ones are explicitly
    # stepped over -- unless the handler moved the program counter,
    # in which case execution just continues at the new location.
    def __run_step(self, *, park: int | None = None) -> bool:
        events = super().run()
        if events & self._BREAKPOINT_HIT:
            addr = self.pc
            if addr == park:
                return False

            self.on_breakpoint()
            if self.pc == addr:
                self.step_over_breakpoint()

        return True

    def __reach_ccp_command_processing(self) -> None:
        while self.__run_step(park=self.__CCP_GET_COMMAND):
            pass

    def bdos_call(self, entry: int, *, de: int | None = None) -> None:
        # Make sure CCP got control and initialised the system.
        self.__reach_ccp_command_processing()

        self.c = entry
        if de is not None:
            self.de = de
        self.__push(self.__CCP_GET_COMMAND)
        self.pc = self.BDOS_ENTRY

        # Execute the call.
        self.__reach_ccp_command_processing()

    def write_str(self, s: str, *, addr: int | None = None) -> None:
        if addr is None:
            addr = self.__TPA
        self.set_memory_block(addr, s.encode('ascii') + b'$')
        self.bdos_call(self.C_WRITESTR, de=addr)

    def get_bdos_version(self) -> tuple[int, int, int]:
        self.bdos_call(self.S_BDOSVER)
        system_type = self.b
        cpm_version = self.a

        cpm_type = (system_type >> 0) & 0xf
        machine_type = (system_type >> 4) & 0xf

        return cpm_version, cpm_type, machine_type

    def __make_fcb(self, filename: str) -> bytes:
        # The type is optional, as in 'dump'.
        name, _, type = filename.partition('.')

        DEFAULT_DRIVE = 0
        drive = DEFAULT_DRIVE

        try:
            name_field = name.upper().encode('ascii')
            type_field = type.upper().encode('ascii')
        except UnicodeEncodeError:
            raise Error(f'invalid filename {filename!r}: not an ASCII name')

        if not 1 <= len(name_field) <= 8:
            raise Error(f'invalid filename {filename!r}: the name must be '
                        '1 to 8 characters')

        if b'.' in type_field or len(type_field) > 3:
            raise Error(f'invalid filename {filename!r}: the type must be '
                        '0 to 3 characters')

        name_field += b' ' * (8 - len(name_field))
        type_field += b' ' * (3 - len(type_field))

        extent = 0

        s1_reserved = b'\x00'
        s2_reserved = b'\x00'

        rc_record_count = 0
        d_reserved = b'\x00' * 16
        cr_current_record = 0

        r0 = b'\x00'
        r1 = b'\x00'
        r2 = b'\x00'

        return (drive.to_bytes(1, 'little') +
                name_field +
                type_field +
                extent.to_bytes(1, 'little') +
                s1_reserved +
                s2_reserved +
                rc_record_count.to_bytes(1, 'little') +
                d_reserved +
                cr_current_record.to_bytes(1, 'little') +
                r0 + r1 + r2)

    # TODO: Support custom FCB addresses, explicit drive
    # specification, file attributes, etc.
    # TODO: Seems to support wildcards?
    def open_file(self, filename: str) -> int:
        FCB = self.__DEFAULT_FCB
        self.set_memory_block(FCB, self.__make_fcb(filename))

        self.bdos_call(self.F_OPEN, de=FCB)

        dir_code = self.a
        if dir_code == 0xff:
            raise Error(f'cannot open file: F_OPEN returned {dir_code}: '
                        'file not found')

        return dir_code

    # TODO: Support custom FCB addresses.
    def close_file(self) -> int:
        self.bdos_call(self.F_CLOSE, de=self.__DEFAULT_FCB)
        dir_code = self.a
        if dir_code == 0xff:
            # TODO: The filename cannot be found in the directory.
            assert 0

        return dir_code

    # Reads the whole file unless given a number of sectors.
    # TODO: Support custom FCB and DMA addresses.
    def read_file(self, num_sectors: int | None = None) -> bytes:
        DMA = self.__TPA
        self.set_dma(DMA)

        sectors: list[bytes] = []
        while num_sectors is None or len(sectors) < num_sectors:
            self.bdos_call(self.F_READ, de=self.__DEFAULT_FCB)

            if self.a != 0:
                break

            sectors.append(bytes(self.memory[DMA:DMA + SECTOR_SIZE]))

        return b''.join(sectors)

    # TODO: Support custom FCB and DMA addresses.
    def write_file(self, data: bytes) -> None:
        DMA = self.__TPA
        self.set_dma(DMA)

        while data:
            chunk = data[0:128]
            data = data[128:]

            chunk += b'\x1a' * (SECTOR_SIZE - len(chunk))
            self.set_memory_block(DMA, chunk)

            self.bdos_call(self.F_WRITE, de=self.__DEFAULT_FCB)
            if self.a != 0:
                raise Error(f'cannot write file: F_WRITE returned {self.a}')

    # TODO: Support custom FCB addresses, explicit drive
    # specification, file attributes, etc.
    # TODO: Throw cpm80 exceptions on problematic input.
    # TODO: Prohibit wildcards.
    # TODO: Delete existing files before creating new ones.
    def make_file(self, filename: str) -> int:
        FCB = self.__DEFAULT_FCB
        self.set_memory_block(FCB, self.__make_fcb(filename))

        # TODO: Before calling this, make sure the file doesn't exist.
        self.bdos_call(self.F_MAKE, de=FCB)

        dir_code = self.a
        if dir_code == 0xff:
            raise Error(f'cannot make file: F_MAKE returned {dir_code}: '
                        'no directory space')

        return dir_code

    # TODO: Support custom FCB addresses, explicit drive
    # specification, file attributes, etc.
    # TODO: Prohibit wildcards?
    def rename_file(self, old: str, new: str) -> int:
        FCB = self.__DEFAULT_FCB
        self.set_memory_block(FCB, (self.__make_fcb(old)[:16] +
                                    self.__make_fcb(new)[:16]))

        self.bdos_call(self.F_RENAME, de=FCB)

        dir_code = self.a
        if dir_code == 0xff:
            raise Error(f'cannot rename file: F_RENAME returned {dir_code}: '
                        'file not found')

        return dir_code

    # TODO: Support custom FCB addresses, explicit drive
    # specification, etc.
    def delete_file(self, filename: str) -> int:
        FCB = self.__DEFAULT_FCB
        self.set_memory_block(FCB, self.__make_fcb(filename))

        self.bdos_call(self.F_DELETE, de=FCB)

        dir_code = self.a
        if dir_code == 0xff:
            raise Error(f'cannot delete file: F_DELETE returned '
                        f'{dir_code}: file not found')

        return dir_code

    def __found_name(self) -> str | None:
        dir_code = self.a
        if dir_code == 0xff:
            return None

        # The matched directory entry sits in the DMA buffer.
        DIR_ENTRY_SIZE = 32
        offset = self.__TPA + dir_code * DIR_ENTRY_SIZE
        entry = self.memory[offset:offset + DIR_ENTRY_SIZE]

        # Mask out the attribute bits.
        name = bytes(b & 0x7f for b in entry[1:9]).decode().strip()
        type = bytes(b & 0x7f for b in entry[9:12]).decode().strip()
        return f'{name}.{type}' if type else name

    # Searches match '?' in the pattern against any character.
    # search_next() continues the search of the last
    # search_first(); file operations in between invalidate it.
    def search_first(self, pattern: str) -> str | None:
        FCB = self.__DEFAULT_FCB
        self.set_memory_block(FCB, self.__make_fcb(pattern))
        self.set_dma(self.__TPA)

        self.bdos_call(self.F_SFIRST, de=FCB)
        return self.__found_name()

    def search_next(self) -> str | None:
        self.bdos_call(self.F_SNEXT, de=self.__DEFAULT_FCB)
        return self.__found_name()

    def set_dma(self, dma: int) -> None:
        self.bdos_call(self.F_DMAOFF, de=dma)

    def on_read_ccp_command(self) -> None:
        assert self.pc == self.__CCP_READ_COMMAND

        COMMAND_SIZE_ADDR = self.__CCP_BASE + 7
        size = self.memory[COMMAND_SIZE_ADDR]

        COMMAND_BUFF = COMMAND_SIZE_ADDR + 1
        b = bytes(self.memory[COMMAND_BUFF:COMMAND_BUFF + size])
        self.__ccp_command_line = b.decode('ascii')

    def on_ccp_command(self) -> None:
        assert self.pc == self.__CCP_RUN_COMMAND
        assert self.__ccp_command_line is not None
        *args, = self.__ccp_command_line.split()
        if len(args) > 0:
            command, *args = args
            if command == 'exit':
                self.__done = True

    # Unlike the CPU's run(), which returns on every event, this runs
    # the machine until the emulation is done, hence the deliberate
    # signature mismatch.
    def run(self) -> None:  # type: ignore[override]
        if self.__frame_ticks == 0:
            while not self.__done:
                self.__run_step()
            return

        # Paced: run a frame's worth of ticks, then sleep off the
        # real time left before the next frame is due.  ticks_to_stop
        # counts down across the breakpoints hit within the frame.
        frame_period = 1 / self.__FRAMES_PER_SECOND
        due = time.monotonic()
        while not self.__done:
            self.ticks_to_stop = self.__frame_ticks
            while not self.__done and self.ticks_to_stop != 0:
                self.__run_step()

            due += frame_period
            now = time.monotonic()
            if now < due:
                time.sleep(due - now)
            elif now - due > frame_period:
                # Fell behind -- for instance after waiting on input
                # -- so give up catching the lost time up.
                due = now


class I8080CPMMachine(CPMMachineMixin, z80.I8080Machine):
    def __init__(self, *,
                 drives: collections.abc.Sequence[DiskDrive] | None = None,
                 console_reader: ConsoleReader | None = None,
                 console_writer: ConsoleWriter | None = None,
                 speed_mhz: float | None = None) -> None:
        z80.I8080Machine.__init__(self)
        CPMMachineMixin.__init__(self, drives=drives,
                                 console_reader=console_reader,
                                 console_writer=console_writer,
                                 speed_mhz=speed_mhz)


# The same CP/M on a Z80 core, for software that uses Z80
# instructions -- the U880 of the Robotron 1715 is a Z80.  The mixin
# is typed against the 8080 machine, so mypy sees its run() override
# as clashing with the Z80 machine's; the override is deliberate, the
# same one I8080CPMMachine gets for free.
class Z80CPMMachine(CPMMachineMixin, z80.Z80Machine):  # type: ignore[misc]
    def __init__(self, *,
                 drives: collections.abc.Sequence[DiskDrive] | None = None,
                 console_reader: ConsoleReader | None = None,
                 console_writer: ConsoleWriter | None = None,
                 speed_mhz: float | None = None) -> None:
        z80.Z80Machine.__init__(self)
        CPMMachineMixin.__init__(self, drives=drives,
                                 console_reader=console_reader,
                                 console_writer=console_writer,
                                 speed_mhz=speed_mhz)


# The files of a disk image, accessed through CP/M itself: the
# operations run on a scratch machine with the image as its disk,
# so the one file system implementation in play is the real BDOS.
class FileSystem:
    def __init__(self, image: DiskImage) -> None:
        self.image = image
        self.__machine = I8080CPMMachine(
            drives=[DiskDrive(image)],
            console_writer=StringDisplay())

    def names(self) -> list[str]:
        names = []
        name = self.__machine.search_first('????????.???')
        while name is not None:
            names.append(name)
            name = self.__machine.search_next()
        return names

    def read(self, filename: str) -> bytes:
        self.__machine.open_file(filename)
        data = self.__machine.read_file()
        self.__machine.close_file()
        return data

    # The file must not exist.  On errors, such as running out of
    # space, no partial file is left behind.
    def write(self, filename: str, data: bytes) -> None:
        self.__machine.make_file(filename)
        try:
            self.__machine.write_file(data)
        except Error:
            # Closing first records the partial file's blocks in
            # the directory; deleting straight away would leave
            # them allocated, as deletion frees what the directory
            # lists.
            self.__machine.close_file()
            self.__machine.delete_file(filename)
            raise

        self.__machine.close_file()

    def delete(self, filename: str) -> None:
        self.__machine.delete_file(filename)


# Holds the terminal in raw mode for a whole interactive session,
# so control keys -- Ctrl+C above all -- reach CP/M as ordinary
# characters to read rather than acting on the host, and the
# terminal leaves the echoing to CP/M's own console handling.  The
# cursor is shown again on the way out in case a program left it
# hidden (see DisplayDevice).  Does nothing without an interactive
# terminal.
@contextlib.contextmanager
def _console_session() -> collections.abc.Iterator[None]:
    if sys.platform != 'win32' and sys.stdin.isatty():
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield
        finally:
            sys.stdout.write('\x1b[?25h')       # ensure cursor shown
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    else:
        yield


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

    console_writer = DisplayDevice(terminal=MACHINES[machine].make_terminal())

    app_dirs = platformdirs.AppDirs('cpm80')
    data_dir = pathlib.Path(app_dirs.user_data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    disk_path = data_dir / f'{machine}.img'
    machine_format = MACHINES[machine].disk_format

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

        m = I8080CPMMachine(drives=drives, console_reader=console_reader,
                            console_writer=console_writer, speed_mhz=speed_mhz)

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
