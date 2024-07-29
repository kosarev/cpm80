#!/usr/bin/env python3

import z80


class _CPMMachineMixin(object):
    __REBOOT = 0x0000
    __TPA = 0x0100

    __BIOS_COLD_BOOT = 0
    __BIOS_WARM_BOOT = 1
    __BIOS_CON_STATUS = 2
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
        with open('bdos-44k.bin', 'rb') as f:
            self.set_memory_block(0x9c00, f.read())

        with open('ccp-44k.bin', 'rb') as f:
            self.set_memory_block(0x9400, f.read())

        BIOS = 0xaa00
        JMP_BIOS = b'\xc3' + BIOS.to_bytes(2, 'little')
        self.set_memory_block(self.__REBOOT, JMP_BIOS)

        for v in range(self.__BIOS_NUM_VECTORS):
            addr = BIOS + v * 3
            self.set_memory_block(addr, b'\xc9')  # ret
            self.set_breakpoint(addr)

    def __handle_breakpoint(self):
        pc = self.pc
        assert 0, 'hit a breakpoint at 0x%04x' % pc

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
