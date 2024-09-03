#!/usr/bin/env python3

import cpm80

# Command-line arguments can be passed to the main() function
# directly.
cpm80.main(['--temp-disk', 'save 0 a.txt', 'ren b.txt=a.txt', 'dir'])
