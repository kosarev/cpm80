#!/usr/bin/env python3

#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80

# Using the StringKeyboard class we can automatically feed CCP
# commands to the emulator.
COMMANDS = (
    'dir',
    'save 1 a.dat',
    'dir',
    )

console_reader = cpm80.StringKeyboard(*COMMANDS)
m = cpm80.I8080CPMMachine(console_reader=console_reader)
m.run()
