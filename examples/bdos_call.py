#!/usr/bin/env python3

import cpm80

m = cpm80.I8080CPMMachine()

# BDOS calls can be performed on the machine object directly:
STR_ADDR = 0x100
m.set_memory_block(STR_ADDR, b'Hello $')
m.bdos_call(m.C_WRITESTR, de=STR_ADDR)

# or by using convenience wrappers:
m.write_str('World!\n')
