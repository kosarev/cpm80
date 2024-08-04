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
        self.blm_allocation_block_mask = 15  # = 2**BSH - 1.
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


class _CPMMachineMixin(object):
    __REBOOT = 0x0000
    __BDOS = 0x0005
    __TPA = 0x0100

    __BIOS_BASE = 0xaa00
    __BIOS_DISK_TABLES_HEAP_BASE = __BIOS_BASE + 0x80

    def __init__(self):
        self.__ctrl_c_count = 0
        self.__cold_boot()

    def __allocate_disk_table_block(self, image):
        addr = self.__disk_tables_heap
        self.__disk_tables_heap += len(image)
        self.set_memory_block(addr, image)
        return addr

    def __set_up_disk_tables(self):
        f = DiskFormat()

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

        self.__disk = DiskImage(f)
        self.__disk_track = 0
        self.__disk_sector = 0

    @staticmethod
    def __load_data(path):
        return importlib.resources.files('cpm80').joinpath(path).read_bytes()

    def __cold_boot(self):
        BDOS_BASE = 0x9c00
        self.set_memory_block(BDOS_BASE, self.__load_data('bdos.bin'))

        JMP = b'\xc3'
        JMP_BIOS = JMP + self.__BIOS_BASE.to_bytes(2, 'little')
        self.set_memory_block(self.__REBOOT, JMP_BIOS)

        BIOS_VECTORS = (
            self.__cold_boot,
            self.__warm_boot,
            self.__console_status,
            self.__console_input,
            self.__console_output,
            self.__list_output,
            self.__punch_output,
            self.__reader_input,
            self.__disk_home,
            self.__select_disk,
            self.__set_track,
            self.__set_sector,
            self.__set_dma,
            self.__read_disk,
            self.__write_disk,
            self.__list_status,
            self.__sector_translate)

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
        self.__warm_boot()

    def __warm_boot(self):
        self.set_memory_block(0x9400, self.__load_data('ccp.bin'))
        self.pc = 0x9400

    def __console_status(self):
        self.a = 0

    def __console_input(self):
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
        else:
            self.__ctrl_c_count = 0

        # Translate backspace.
        if ch == 127:
            ch = 8

        self.a = ch & 0x7f

    def __console_output(self):
        sys.stdout.write(chr(self.c))
        sys.stdout.flush()

    def __list_output(self):
        assert 0  # TODO

    def __punch_output(self):
        assert 0  # TODO

    def __reader_input(self):
        assert 0  # TODO

    def __disk_home(self):
        self.__disk_track = 0

    def __select_disk(self):
        DISK_A = 0
        if self.c == DISK_A:
            self.hl = self.__disk_header_table
            return

        self.hl = 0

    def __set_track(self):
        self.__disk_track = self.bc

    def __set_sector(self):
        self.__disk_sector = self.bc

    def __set_dma(self):
        self.__dma = self.bc

    def __read_disk(self):
        data = self.__disk.get_sector(self.__disk_sector, self.__disk_track)
        self.memory[self.__dma:self.__dma + SECTOR_SIZE] = data
        self.a = 0  # Read OK.

    def __write_disk(self):
        data = self.__disk.get_sector(self.__disk_sector, self.__disk_track)
        data[:] = self.memory[self.__dma:self.__dma + SECTOR_SIZE]
        self.a = 0  # Write OK.

    def __list_status(self):
        assert 0  # TODO

    def __sector_translate(self):
        translate_table = self.de
        assert translate_table == 0x0000

        logical_sector = self.bc
        physical_sector = logical_sector
        self.hl = physical_sector

    def __handle_breakpoint(self):
        v = self.__bios_vectors.get(self.pc)
        if v:
            v()

    def run(self):
        while True:
            events = super().run()

            if events & self._BREAKPOINT_HIT:
                self.__handle_breakpoint()

            if self.__ctrl_c_count >= 3:
                break


class I8080CPMMachine(_CPMMachineMixin, z80.I8080Machine):
    def __init__(self):
        z80.I8080Machine.__init__(self)
        _CPMMachineMixin.__init__(self)


def main():
    m = I8080CPMMachine()
    m.run()


if __name__ == "__main__":
    main()
