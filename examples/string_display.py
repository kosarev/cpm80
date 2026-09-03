#!/usr/bin/env python3

#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80

# Collect emulator output into a string.
d = cpm80.StringDisplay()

m = cpm80.I8080CPMMachine(
    console_reader=cpm80.StringKeyboard('dir'),
    console_writer=d)

m.run()

print(d.string)
