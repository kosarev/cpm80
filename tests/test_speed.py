#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import time

import cpm80

# A delay loop of 65536 iterations (about 1.5 million ticks),
# followed by console reads that the reader stops the machine on.
_PROGRAM = bytes((
    0x11, 0x00, 0x00,   # lxi d, 0
    0x1b,               # dcx d
    0x7a,               # mov a, d
    0xb3,               # ora e
    0xc2, 0x03, 0x01,   # jnz 0x103
    0x0e, 0x01,         # mvi c, 1  (C_READ)
    0xcd, 0x05, 0x00,   # call 5
    0xc3, 0x09, 0x01))  # jmp back to read


class _StopReader:
    def input(self) -> int | None:
        return None

    def ready(self) -> bool:
        return False


def _time_at(speed_mhz: float | None) -> float:
    m = cpm80.I8080CPMMachine(console_reader=_StopReader(),
                              console_writer=cpm80.StringDisplay(),
                              speed_mhz=speed_mhz)
    m.set_memory_block(0x100, _PROGRAM)
    m.pc = 0x100
    start = time.monotonic()
    m.run()
    return time.monotonic() - start


def test_pacing_slows_execution() -> None:
    # The workload is a fraction of a second unlimited, but about
    # 1.5 seconds at 1 MHz.  Wide bounds keep the test robust.
    assert _time_at(None) < 0.5
    assert 0.8 < _time_at(1.0) < 4.0


def test_higher_speed_is_faster() -> None:
    assert _time_at(4.0) < _time_at(1.0)
