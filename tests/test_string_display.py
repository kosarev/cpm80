import cpm80


def test_basic() -> None:
    d = cpm80.StringDisplay()
    for c in 'user 0\ndir\ntype a.txt\n':
        d.output(ord(c))
    assert d.string == 'user 0\ndir\ntype a.txt\n'
