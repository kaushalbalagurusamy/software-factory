def add_one(x: int) -> int:
    return x + 1


def add_one_guarded(x: int) -> int:
    if x >= 9223372036854775807:
        raise OverflowError("would overflow")
    return x + 1
