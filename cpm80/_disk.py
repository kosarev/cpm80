#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import collections.abc

from ._error import Error

SECTOR_SIZE = 128


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
