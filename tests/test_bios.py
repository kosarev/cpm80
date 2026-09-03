#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import z80

import cpm80


def test_bios_vectors_via_reboot_jump() -> None:
    # Programs locate the BIOS by reading the WBOOT address stored
    # at 0x0001 and indexing the vectors relative to it.  This
    # program prints 'A' by calling CONOUT, three vectors past
    # WBOOT.  The RET in the vector then pops a zero return address
    # off the fresh stack, and the jump at zero warm-boots into the
    # CCP, which proves the stored address is WBOOT itself and not
    # some other vector.
    TPA = 0x100
    code = z80.Code()
    code.start_block(TPA)
    code.add(
        z80.LD(z80.HL, z80.At(0x0001)),
        z80.LD(z80.DE, 9),
        z80.ADD(z80.HL, z80.DE),
        z80.LD(z80.C, ord('A')),
        z80.JP(z80.At(z80.HL)))
    code.resolve()
    addr, program = code.encode()[0]

    d = cpm80.StringDisplay()
    m = cpm80.I8080CPMMachine(console_reader=cpm80.StringKeyboard(),
                              console_writer=d)
    m.set_memory_block(addr, program)
    m.pc = addr
    m.run()

    assert d.string.startswith('A')
    assert 'A>' in d.string


def test_default_dma() -> None:
    drive = cpm80.DiskDrive()
    marker = bytes(range(128))
    drive.image.get_sector(1, 0)[:] = marker

    # A read with no SETDMA call goes to the default DMA address.
    m = cpm80.I8080CPMMachine(drives=[drive])
    drive.current_sector = 1
    m.on_read()

    DEFAULT_DMA = 0x80
    assert bytes(m.memory[DEFAULT_DMA:DEFAULT_DMA + 128]) == marker
    assert m.a == 0


def test_sector_io_errors() -> None:
    drive = cpm80.DiskDrive()
    m = cpm80.I8080CPMMachine(drives=[drive])

    # Transfers outside the disk report an error rather than crash
    # or alias into another track.
    drive.current_sector = drive.format.sectors_per_track
    m.on_read()
    assert m.a == 1
    m.on_write()
    assert m.a == 1
