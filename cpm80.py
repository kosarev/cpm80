#!/usr/bin/env python3

import sys
import termios
import tty
import z80


class _CPMMachineMixin(object):
    __REBOOT = 0x0000
    __BDOS = 0x0005
    __TPA = 0x0100

    __BIOS_BASE = 0xaa00

    __BIOS_COLD_BOOT = 0
    __BIOS_WARM_BOOT = 1
    __BIOS_CONSOLE_STATUS = 2
    __BIOS_CONSOLE_INPUT = 3
    __BIOS_CONSOLE_OUTPUT = 4
    __BIOS_LIST_OUTPUT = 5
    __BIOS_PUNCH_OUTPUT = 6
    __BIOS_READER_INPUT = 7
    __BIOS_DISK_HOME = 8
    __BIOS_SELECT_DISK = 9
    __BIOS_SET_TRACK = 10
    __BIOS_SET_SECTOR = 11
    __BIOS_SET_DMA = 12
    __BIOS_READ_DISK = 13
    __BIOS_WRITE_DISK = 14
    __BIOS_LIST_STATUS = 15
    __BIOS_SECTOR_TRANSLATE = 16
    __BIOS_NUM_VECTORS = 17

    __BIOS_DISK_TABLES_HEAP_BASE = __BIOS_BASE + 0x80

    def __init__(self):
        self.__cold_boot()

    def __allocate_disk_table_block(self, image):
        addr = self.__disk_tables_heap
        self.__disk_tables_heap += len(image)
        self.set_memory_block(addr, image)
        return addr

    def __set_up_disk_tables(self):
        bls_block_size = 2048
        spt_sectors_per_track = 40
        bsh_block_shift_factor = 4
        blm_allocation_block_mask = 15  # Depends on BSH.
        exm_extent_mask = 1  # EXM = 1 and DSM < 256 means BLS = 2048.
        dsm_disk_size_max = 194  # In BLS units.
        drm_max_dir_entry = 63
        al0_allocation_mask = 128  # 1 block for 64 dirs, 32 bytes each.
        al1_allocation_mask = 0
        cks_directory_check_size = 16
        off_system_tracks_offset = 2

        removable = True
        cks = (drm_max_dir_entry + 1) // 4 if removable else 0

        # Shared by all identical drives.
        dpb_disk_param_block = self.__allocate_disk_table_block(
            spt_sectors_per_track.to_bytes(2, 'little') +
            bsh_block_shift_factor.to_bytes(1, 'little') +
            blm_allocation_block_mask.to_bytes(1, 'little') +
            exm_extent_mask.to_bytes(1, 'little') +
            dsm_disk_size_max.to_bytes(2, 'little') +
            drm_max_dir_entry.to_bytes(2, 'little') +
            al0_allocation_mask.to_bytes(1, 'little') +
            al1_allocation_mask.to_bytes(1, 'little') +
            cks_directory_check_size.to_bytes(2, 'little') +
            off_system_tracks_offset.to_bytes(2, 'little'))

        # Shared by all drives.
        dirbuf_scratch_pad = self.__allocate_disk_table_block(b'\x00' * 128)

        xlt_sector_translation_vector = 0x0000
        bdos_scratch_pad = 0x0000
        csv_scratch_pad = self.__allocate_disk_table_block(b'\x00' * cks)
        alv_scratch_pad = self.__allocate_disk_table_block(
            b'\x00' * (dsm_disk_size_max // 8 + 1))

        self.__disk_header_table = self.__allocate_disk_table_block(
            xlt_sector_translation_vector.to_bytes(2, 'little') +
            bdos_scratch_pad.to_bytes(2, 'little') +
            dirbuf_scratch_pad.to_bytes(2, 'little') +
            dpb_disk_param_block.to_bytes(2, 'little') +
            csv_scratch_pad.to_bytes(2, 'little') +
            alv_scratch_pad.to_bytes(2, 'little'))

        disk_size = (dsm_disk_size_max + 1) * bls_block_size
        self.__disk_image = bytearray(disk_size)

    def __cold_boot(self):
        with open('bdos-44k.bin', 'rb') as f:
            BDOS_BASE = 0x9c00
            self.set_memory_block(BDOS_BASE, f.read())

        JMP = b'\xc3'
        JMP_BIOS = JMP + self.__BIOS_BASE.to_bytes(2, 'little')
        self.set_memory_block(self.__REBOOT, JMP_BIOS)

        for v in range(self.__BIOS_NUM_VECTORS):
            addr = self.__BIOS_BASE + v * 3
            self.set_memory_block(addr, b'\xc9')  # ret
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
        with open('ccp-44k.bin', 'rb') as f:
            self.set_memory_block(0x9400, f.read())

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
            sys.exit()

        self.a = ch & 0x7f

    def __console_output(self):
        sys.stdout.write(chr(self.c))
        sys.stdout.flush()

    def __select_disk(self):
        DISK_A = 0
        if self.c == DISK_A:
            return self.__disk_header_table

        self.hl = 0

    def __set_dma(self):
        self.__dma = self.bc

    def __handle_breakpoint(self):
        pc = self.pc
        offset = pc - self.__BIOS_BASE
        assert offset >= 0 and offset % 3 == 0

        v = offset // 3
        assert v < self.__BIOS_NUM_VECTORS

        if v == self.__BIOS_COLD_BOOT:
            self.__cold_boot()
        elif v == self.__BIOS_WARM_BOOT:
            self.__warm_boot()
        elif v == self.__BIOS_CONSOLE_STATUS:
            self.__console_status()
        elif v == self.__BIOS_CONSOLE_INPUT:
            self.__console_input()
        elif v == self.__BIOS_CONSOLE_OUTPUT:
            self.__console_output()
        elif v == self.__BIOS_SELECT_DISK:
            self.__select_disk()
        elif v == self.__BIOS_SET_DMA:
            self.__set_dma()
        else:
            assert 0, f'hit BIOS vector {v}'

    def run(self):
        while True:
            events = super().run()

            if events & self._BREAKPOINT_HIT:
                self.__handle_breakpoint()


class I8080CPMMachine(_CPMMachineMixin, z80.I8080Machine):
    def __init__(self):
        z80.I8080Machine.__init__(self)
        _CPMMachineMixin.__init__(self)


def main():
    m = I8080CPMMachine()
    m.run()


if __name__ == "__main__":
    main()
