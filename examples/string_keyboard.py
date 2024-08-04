#!/usr/bin/env python3

import cpm80

# Using the StringKeyboard class we can automatically feed CCP
# commands to the emulator.
COMMANDS = (
    'dir',
    'save 1 a.dat',
    'dir',
    '',  # Empty line to see the output of the last 'dir'.
    )

console_reader = cpm80.StringKeyboard(*COMMANDS)
m = cpm80.I8080CPMMachine(console_reader=console_reader)
m.run()
