# cpm80
CP/M-80 2.2 emulator with Python API.

[![Python package CI](https://github.com/kosarev/cpm80/actions/workflows/python-package.yml/badge.svg)](https://github.com/kosarev/cpm80/actions/workflows/python-package.yml)
[![PyPI](https://img.shields.io/pypi/v/cpm80)](https://pypi.org/project/cpm80/)
[![Python](https://img.shields.io/pypi/pyversions/cpm80)](https://pypi.org/project/cpm80/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/kosarev/cpm80/blob/main/LICENSE)


Based on the fast and flexible [z80](https://github.com/kosarev/z80) emulator.


## Installing

```shell
$ pip install cpm80
```


## Running and terminating

```
$ cpm80
44k CP/M vers 2.2

A>save 1 dump.dat
A>dir
A: DUMP     DAT
A>exit
```

Enter `exit` or just hit <kbd>Ctrl</kbd> + <kbd>C</kbd> three
times to quit the emulator.


## Exchanging files with the host

The directory cpm80 starts in is mounted as drive B:, and fresh
disks come with PIP, so files just copy.

```
$ ls
hello.txt
$ cpm80
44k CP/M vers 2.2

A>dir b:
B: HELLO    TXT
A>pip a:=b:hello.txt
A>save 1 b:dump.dat
A>exit
$ ls
DUMP.DAT  hello.txt
```

A single <kbd>Ctrl</kbd> + <kbd>C</kbd> re-reads the directory --
the usual CP/M way of telling the system the disk has changed.


## Running commands automatically

From the command line:

```shell
$ cpm80 dir 'save 1 a.dat' dir
```

Alternatively, we can use the API's `StringKeyboard` class to
feed arbitrary commands to the command processor, CCP, thus
replacing `KeyboardDevice` console readers used by default:

```python3
import cpm80

COMMANDS = (
    'dir',
    'save 1 a.dat',
    'dir',
    )

console_reader = cpm80.StringKeyboard(*COMMANDS)
m = cpm80.I8080CPMMachine(console_reader=console_reader)
m.run()
```
[string_keyboard.py](https://github.com/kosarev/cpm80/blob/main/examples/string_keyboard.py)

Output:
```
44k CP/M vers 2.2

A>dir
NO FILE
A>save 1 a.dat
A>dir
A: A        DAT
A>
```

## Getting output as a string

Similarly, we can replace `DisplayDevice` console writers used by
default with custom writers to do special work for the emulator's
output.
For example, one could use a `StringDisplay` writer to gather the
output into a string.

```python3
d = cpm80.StringDisplay()

m = cpm80.I8080CPMMachine(
    console_reader=cpm80.StringKeyboard('dir'),
    console_writer=d)

m.run()

print(d.string)
```
[string_display.py](https://github.com/kosarev/cpm80/blob/main/examples/string_display.py)


## Making BDOS calls

BDOS calls can be performed on the machine object directly or by
using convenience wrappers.

```python3
m = cpm80.I8080CPMMachine()

STR_ADDR = 0x100
m.set_memory_block(STR_ADDR, b'Hello $')
m.bdos_call(m.C_WRITESTR, de=STR_ADDR)

m.write_str('World!\n')
```
[bdos_call.py](https://github.com/kosarev/cpm80/blob/main/examples/bdos_call.py)


## Working with files

Similarly, using BDOS wrappers one can manipulate files on disks.

```python3
drive = cpm80.DiskDrive()

m = cpm80.I8080CPMMachine(drives=[drive])
m.make_file('file.txt')
m.write_file(f'bin(100) is {bin(100)}\n'.encode())
m.close_file()
del m

# Then read and print the contents of the file using another machine.
m = cpm80.I8080CPMMachine(drives=[drive])
m.open_file('file.txt')
print(m.read_file())
m.close_file()
```
[doing_files.py](https://github.com/kosarev/cpm80/blob/main/examples/doing_files.py)
