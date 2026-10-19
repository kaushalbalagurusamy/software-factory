"""Functions outside the verified subset (each must be UNSUPPORTED, never approximated)."""


def helper(x: int) -> int:
    return x + 1


def sum_to(n: int) -> int:
    total = 0
    i = 0
    while i < n:
        total += i
        i += 1
    return total


def calls_helper(x: int) -> int:
    return helper(x)


def uses_float(x: int) -> int:
    return int(x * 0.5)
