"""Known-good implementations (fixture for the verification gate tests)."""


def clamp(x: int, lo: int, hi: int) -> int:
    if x < lo:
        return lo
    elif x > hi:
        return hi
    return x


def my_abs(x: int) -> int:
    return -x if x < 0 else x


def floor_div(a: int, b: int) -> int:
    return a // b


def floor_mod(a: int, b: int) -> int:
    return a % b


def safe_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("b is zero")
    return a // b


def max3(a: int, b: int, c: int) -> int:
    return max(a, b, c)


def is_even(n: int) -> bool:
    return n % 2 == 0
