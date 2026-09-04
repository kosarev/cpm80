#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""The files of a disk image, accessed through CP/M itself.

The operations run on a scratch machine with the image as its disk,
so the one file system implementation in play is the real BDOS.  The
core classes it drives live in the package it is part of, so they are
imported where used, to avoid an import cycle.
"""

import typing

if typing.TYPE_CHECKING:
    from . import DiskImage


class FileSystem:
    def __init__(self, image: 'DiskImage') -> None:
        from . import DiskDrive, I8080CPMMachine, StringDisplay
        self.image = image
        self.__machine = I8080CPMMachine(
            drives=[DiskDrive(image)],
            console_writer=StringDisplay())

    def names(self) -> list[str]:
        names = []
        name = self.__machine.search_first('????????.???')
        while name is not None:
            names.append(name)
            name = self.__machine.search_next()
        return names

    def read(self, filename: str) -> bytes:
        self.__machine.open_file(filename)
        data = self.__machine.read_file()
        self.__machine.close_file()
        return data

    # The file must not exist.  On errors, such as running out of
    # space, no partial file is left behind.
    def write(self, filename: str, data: bytes) -> None:
        from . import Error
        self.__machine.make_file(filename)
        try:
            self.__machine.write_file(data)
        except Error:
            # Closing first records the partial file's blocks in
            # the directory; deleting straight away would leave
            # them allocated, as deletion frees what the directory
            # lists.
            self.__machine.close_file()
            self.__machine.delete_file(filename)
            raise

        self.__machine.close_file()

    def delete(self, filename: str) -> None:
        self.__machine.delete_file(filename)
