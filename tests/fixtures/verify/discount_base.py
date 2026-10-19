"""Base version of apply_discount: never returns a negative price."""


def apply_discount(price: int, discount: int) -> int:
    return max(price - discount, 0)
