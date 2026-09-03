#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80


def test_bios_vectors_via_reboot_jump() -> None:
    # Programs locate the BIOS by reading the WBOOT address stored
    # at 0x0001 and indexing the vectors relative to it.  This
    # program prints 'A' by calling CONOUT, three vectors past
    # WBOOT.  The RET in the vector then pops a zero return address
    # off the fresh stack, and the jump at zero warm-boots into the
    # CCP, which proves the stored address is WBOOT itself and not
    # some other vector.
    PROGRAM = bytes((
        0x2a, 0x01, 0x00,   # lhld 0x0001
        0x11, 0x09, 0x00,   # lxi d, 9
        0x19,               # dad d
        0x0e, ord('A'),     # mvi c, 'A'
        0xe9))              # pchl

    d = cpm80.StringDisplay()
    m = cpm80.I8080CPMMachine(console_reader=cpm80.StringKeyboard(),
                              console_writer=d)
    m.set_memory_block(0x100, PROGRAM)
    m.pc = 0x100
    m.run()

    assert d.string.startswith('A')
    assert 'A>' in d.string


def test_default_dma() -> None:
    drive = cpm80.DiskDrive()
    marker = bytes(range(128))
    drive.image.get_sector(1, 0)[:] = marker

    # A read with no SETDMA call goes to the default DMA address.
    m = cpm80.I8080CPMMachine(drive=drive)
    drive.current_sector = 1
    m.on_read()

    DEFAULT_DMA = 0x80
    assert bytes(m.memory[DEFAULT_DMA:DEFAULT_DMA + 128]) == marker
    assert m.a == 0
