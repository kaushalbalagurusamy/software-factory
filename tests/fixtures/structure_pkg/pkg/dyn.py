"""Names that reach core only through a star import, plus dynamic code."""


def star_made():
    return 1


def evil(source):
    return eval(source)
