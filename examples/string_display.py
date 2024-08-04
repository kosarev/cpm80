#!/usr/bin/env python3

import cpm80

# Collect emulator output into a string.
d = cpm80.StringDisplay()

m = cpm80.I8080CPMMachine(
    console_reader=cpm80.StringKeyboard('dir', ''),
    console_writer=d)

m.run()

print(d.string)
