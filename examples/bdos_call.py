#!/usr/bin/env python3

#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80

m = cpm80.I8080CPMMachine()

# BDOS calls can be performed on the machine object directly:
STR_ADDR = 0x100
m.set_memory_block(STR_ADDR, b'Hello $')
m.bdos_call(m.C_WRITESTR, de=STR_ADDR)

# or by using convenience wrappers:
m.write_str('World!\n')
