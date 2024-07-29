#!/usr/bin/env python3

import z80


class _CPMMachineMixin(object):
    __REBOOT = 0x0000
    __BDOS = 0x0005
    __TPA = 0x0100

    __BIOS_BASE = 0xaa00

    __BIOS_COLD_BOOT = 0
    __BIOS_WARM_BOOT = 1
    __BIOS_CONSOLE_STATUS = 2
    __BIOS_CON_INPUT = 3
    __BIOS_CON_OUTPUT = 4
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

    def __init__(self):
        self.__cold_boot()

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

    def __select_disk(self):
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
