# cpm80
CP/M-80 2.2 emulator with Python API.

![Python Package CI](https://github.com/kosarev/cpm80/actions/workflows/python-package.yml/badge.svg?cache-control=no-cache)


Based on the fast and flexible [z80](https://github.com/kosarev/z80) emulator.


## Installing

```shell
$ pip install cpm80
```


## Running and terminating

```
$ cpm80

>save 1 dump.dat
A>dir
A: DUMP     DAT
A>exit
```

Enter `exit` or just hit <kbd>Ctrl</kbd> + <kbd>C</kbd> three
times to quit the emulator.


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
[string_keyboard.py](https://github.com/kosarev/cpm80/blob/master/examples/string_keyboard.py)

Output:
```
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
[string_display.py](https://github.com/kosarev/cpm80/blob/master/examples/string_display.py)


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
[bdos_call.py](https://github.com/kosarev/cpm80/blob/master/examples/bdos_call.py)


## Working with files

Similarly, using BDOS wrappers one can manipulate files on disks.

```python3
drive = cpm80.DiskDrive()

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
```
[doing_files.py](https://github.com/kosarev/cpm80/blob/master/examples/doing_files.py)
