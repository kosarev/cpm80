#!/usr/bin/env python3

import importlib.resources
import sys
import termios
import tty
import z80

SECTOR_SIZE = 128


class DiskFormat(object):
    def __init__(self):
        self.bls_block_size = 2048
        self.spt_sectors_per_track = 40
        self.bsh_block_shift_factor = 4
        self.blm_allocation_block_mask = 2**self.bsh_block_shift_factor - 1
        assert self.blm_allocation_block_mask == 15
        self.exm_extent_mask = 1  # EXM = 1 and DSM < 256 means BLS = 2048.
        self.dsm_disk_size_max = 194  # In BLS units.
        self.drm_max_dir_entry = 63
        self.al0_allocation_mask = 128  # 1 block for 64 dirs, 32 bytes each.
        self.al1_allocation_mask = 0
        self.cks_directory_check_size = 16
        self.off_system_tracks_offset = 2
        self.removable = True
        self.skew_factor = 0  # No translation.

        self.disk_size = (self.dsm_disk_size_max + 1) * self.bls_block_size

    def translate_sector(self, logical_sector):
        # TODO: Support arbitrary skew factors.
        assert self.skew_factor == 0
        physical_sector = logical_sector
        return physical_sector


class DiskImage(object):
    def __init__(self, format):
        self.format = format

        size = format.disk_size
        self.image = bytearray(size)
        self.image[:] = b'\xe5' * size

    def get_sector(self, sector, track):
        sector_index = sector + track * self.format.spt_sectors_per_track
        offset = sector_index * SECTOR_SIZE
        return memoryview(self.image)[offset:offset + SECTOR_SIZE]

    def translate_sector(self, logical_sector):
        return self.format.translate_sector(logical_sector)


class DiskDrive(object):
    def __init__(self, image):
        self.image = image
        self.current_sector = 0
        self.current_track = 0

    @property
    def format(self):
        return self.image.format

    def translate_sector(self, logical_sector):
        return self.image.translate_sector(logical_sector)

    def read_sector(self):
        sector = self.image.get_sector(self.current_sector, self.current_track)
        return bytes(sector)

    def write_sector(self, data):
        assert len(data) == SECTOR_SIZE
        sector = self.image.get_sector(self.current_sector, self.current_track)
        sector[:] = data


class KeyboardDevice(object):
    def __init__(self):
        self.__ctrl_c_count = 0

    def input(self):
        # Borrowed from:
        # https://stackoverflow.com/questions/510357/how-to-read-a-single-character-from-the-user
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = ord(sys.stdin.read(1))
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

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


class StringKeyboard(object):
    def __init__(self, *commands):
        self.__input = '\n'.join(commands) + '\n'
        self.__i = 0

    def input(self):
        if self.__i >= len(self.__input):
            return None

        c = self.__input[self.__i]
        self.__i += 1
        return ord(c)


class DisplayDevice(object):
    def output(self, c):
        sys.stdout.write(chr(c))
        sys.stdout.flush()


class StringDisplay(object):
    def __init__(self):
        self.__output = []

    def output(self, c):
        self.__output.append(c)

    @property
    def string(self):
        return ''.join(chr(c) for c in self.__output)


class CPMMachineMixin(object):
    __REBOOT = 0x0000
    __BDOS = 0x0005
    __TPA = 0x0100

    __BIOS_BASE = 0xaa00
    __BIOS_DISK_TABLES_HEAP_BASE = __BIOS_BASE + 0x80

    def __init__(self, *, console_reader=None, console_writer=None):
        self.__console_reader = console_reader or KeyboardDevice()
        self.__console_writer = console_writer or DisplayDevice()
        self.__done = False
        self.boot_cold_boot()

    def __allocate_disk_table_block(self, image):
        addr = self.__disk_tables_heap
        self.__disk_tables_heap += len(image)
        self.set_memory_block(addr, image)
        return addr

    def __set_up_disk_tables(self):
        self.__drive = DiskDrive(DiskImage(DiskFormat()))
        f = self.__drive.format

        # Shared by all identical drives.
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

        # Shared by all drives.
        dirbuf_scratch_pad = self.__allocate_disk_table_block(b'\x00' * 128)

        xlt_sector_translation_vector = 0x0000
        bdos_scratch_pad1 = 0x0000
        bdos_scratch_pad2 = 0x0000
        bdos_scratch_pad3 = 0x0000
        cks = (f.drm_max_dir_entry + 1) // 4 if f.removable else 0
        csv_scratch_pad = self.__allocate_disk_table_block(b'\x00' * cks)
        alv_scratch_pad = self.__allocate_disk_table_block(
            b'\x00' * (f.dsm_disk_size_max // 8 + 1))

        self.__disk_header_table = self.__allocate_disk_table_block(
            xlt_sector_translation_vector.to_bytes(2, 'little') +
            bdos_scratch_pad1.to_bytes(2, 'little') +
            bdos_scratch_pad2.to_bytes(2, 'little') +
            bdos_scratch_pad3.to_bytes(2, 'little') +
            dirbuf_scratch_pad.to_bytes(2, 'little') +
            dpb_disk_param_block.to_bytes(2, 'little') +
            csv_scratch_pad.to_bytes(2, 'little') +
            alv_scratch_pad.to_bytes(2, 'little'))

    @staticmethod
    def __load_data(path):
        return importlib.resources.files('cpm80').joinpath(path).read_bytes()

    def boot_cold_boot(self):
        BDOS_BASE = 0x9c00
        self.set_memory_block(BDOS_BASE, self.__load_data('bdos.bin'))

        JMP = b'\xc3'
        JMP_BIOS = JMP + self.__BIOS_BASE.to_bytes(2, 'little')
        self.set_memory_block(self.__REBOOT, JMP_BIOS)

        BIOS_VECTORS = (
            self.boot_cold_boot,
            self.wboot_warm_boot,
            self.const_console_status,
            self.conin_console_input,
            self.conout_console_output,
            self.list_output,
            self.punch_output,
            self.reader_input,
            self.home_disk_home,
            self.seldsk_select_disk,
            self.settrk_set_track,
            self.setsec_set_sector,
            self.setdma_set_dma,
            self.read_disk,
            self.write_disk,
            self.listst_list_status,
            self.sectran_sector_translate)

        self.__bios_vectors = {}
        for i, v in enumerate(BIOS_VECTORS):
            addr = self.__BIOS_BASE + i * 3
            self.__bios_vectors[addr] = v
            RET = b'\xc9'
            self.set_memory_block(addr, RET)
            self.set_breakpoint(addr)

        self.__disk_tables_heap = self.__BIOS_DISK_TABLES_HEAP_BASE
        self.__set_up_disk_tables()

        self.sp = 0x100

        self.__dma_addr = 0x80

        BDOS_ENTRY = BDOS_BASE + 0x11
        JMP_BDOS = JMP + BDOS_ENTRY.to_bytes(2, 'little')
        self.set_memory_block(self.__BDOS, JMP_BDOS)

        CURRENT_DISK = 0
        CURRENT_DISK_ADDR = 0x0004
        self.set_memory_block(CURRENT_DISK_ADDR,
                              CURRENT_DISK.to_bytes(1, 'little'))

        self.c = CURRENT_DISK
        self.wboot_warm_boot()

    def wboot_warm_boot(self):
        self.set_memory_block(0x9400, self.__load_data('ccp.bin'))
        self.pc = 0x9400

    def const_console_status(self):
        self.a = 0

    def conin_console_input(self):
        c = self.__console_reader.input()
        if c is None:
            self.__done = True
            return

        self.a = c

    def conout_console_output(self):
        self.__console_writer.output(self.c)

    def list_output(self):
        assert 0  # TODO

    def punch_output(self):
        assert 0  # TODO

    def reader_input(self):
        assert 0  # TODO

    def home_disk_home(self):
        self.__drive.current_track = 0

    def seldsk_select_disk(self):
        DISK_A = 0
        if self.c == DISK_A:
            self.hl = self.__disk_header_table
            return

        self.hl = 0

    def settrk_set_track(self):
        self.__drive.current_track = self.bc

    def setsec_set_sector(self):
        self.__drive.current_sector = self.bc

    def setdma_set_dma(self):
        self.__dma = self.bc

    def read_disk(self):
        self.set_memory_block(self.__dma, self.__drive.read_sector())
        self.a = 0  # Read OK.

    def write_disk(self):
        data = self.memory[self.__dma:self.__dma + SECTOR_SIZE]
        self.__drive.write_sector(data)
        self.a = 0  # Write OK.

    def listst_list_status(self):
        assert 0  # TODO

    def sectran_sector_translate(self):
        self.hl = self.__drive.translate_sector(self.bc)

    def handle_breakpoint(self):
        v = self.__bios_vectors.get(self.pc)
        if v:
            v()

    def run(self):
        while True:
            events = super().run()

            if events & self._BREAKPOINT_HIT:
                self.handle_breakpoint()

            if self.__done:
                break


class I8080CPMMachine(CPMMachineMixin, z80.I8080Machine):
    def __init__(self, *, console_reader=None, console_writer=None):
        z80.I8080Machine.__init__(self)
        CPMMachineMixin.__init__(self, console_reader=console_reader,
                                 console_writer=console_writer)


def main(args=None):
    import argparse
    parser = argparse.ArgumentParser(description='CP/M-80 2.2 emulator.')
    parser.add_argument('-c', '--commands', metavar='CMD', type=str, nargs='+',
                        help='run commands as if they were typed in manually')
    args = parser.parse_args(args)

    if args.commands is None:
        console_reader = KeyboardDevice()
    else:
        console_reader = StringKeyboard(*args.commands)

    m = I8080CPMMachine(console_reader=console_reader)
    m.run()


if __name__ == '__main__':
    main()
