def apply_discount(price: int, discount: int) -> int:
    if discount > price:
        return 0
    return price - discount
