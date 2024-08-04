# cpm80
CP/M-80 2.2 emulator with Python API.

Based on the fast and flexible [z80](https://github.com/kosarev/z80) emulator.


## Installing

```shell
$ pip install cpm80
```


## Running and terminating

```
$ cpm80

A>save 1 dump.dat
A>dir
A: DUMP     DAT
A>^C
A>^C
A>
```

Press <kbd>Ctrl</kbd> + <kbd>C</kbd> three times to exit.


## Running commands automatically

Using the `StringKeyboard` class we can automatically feed
commands to the command processor, CCP.

```python3
import cpm80

COMMANDS = (
    'dir',
    'save 1 a.dat',
    'dir',
    '',  # Empty line to see the output of the last 'dir'.
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
