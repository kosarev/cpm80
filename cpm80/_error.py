#   CP/M-80 2.2 emulator.
#   https://github.com/kosarev/cpm80
#
#   Copyright (C) 2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


# Raised for every cpm80 failure: a bad disk image, a full disk, an
# unmountable name.
class Error(BaseException):
    pass
