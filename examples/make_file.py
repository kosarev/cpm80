#!/usr/bin/env python3

import cpm80


drive = cpm80.DiskDrive()

# Create a file on the disk using one machine instance.
m = cpm80.I8080CPMMachine(drive=drive)
m.make_file('file.txt')
m.write_file(f'bin(100) is {bin(100)}\n'.encode())
m.close_file()
del m

# Then read and print the contents of the file using another machine.
m = cpm80.I8080CPMMachine(drive=drive)
m.open_file('file.txt')
print(m.read_file())
m.close_file()
