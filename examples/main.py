#!/usr/bin/env python3

#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2024-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cpm80

# Command-line arguments can be passed to the main() function
# directly.
cpm80.main(['--no-automount', 'save 0 a.txt', 'ren b.txt=a.txt', 'dir'])
