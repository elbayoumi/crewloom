def quote(order):
    """Calculate an order quote using exact integer arithmetic.

    Raise ValueError for malformed input without modifying the order.
    """
    def integer(value, name, minimum=0, maximum=None):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f"{name} is out of range")
        return value

    if not isinstance(order, dict):
        raise ValueError("order must be a dict")
    if not order.keys() <= {"lines", "discount_bps", "tax_bps", "shipping_cents"}:
        raise ValueError("order contains unknown fields")

    lines = order.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("lines must be a nonempty list")

    discount_bps = integer(order.get("discount_bps", 0), "discount_bps", maximum=10000)
    tax_bps = integer(order.get("tax_bps", 0), "tax_bps", maximum=10000)
    shipping = integer(order.get("shipping_cents", 0), "shipping_cents")

    subtotal = 0
    for line in lines:
        if not isinstance(line, dict) or line.keys() != {"price_cents", "quantity"}:
            raise ValueError("each line must contain exactly price_cents and quantity")
        price = integer(line["price_cents"], "price_cents")
        quantity = integer(line["quantity"], "quantity", minimum=1)
        subtotal += price * quantity

    discount = (subtotal * discount_bps + 5000) // 10000
    tax = ((subtotal - discount) * tax_bps + 5000) // 10000
    return {
        "subtotal_cents": subtotal,
        "discount_cents": discount,
        "tax_cents": tax,
        "total_cents": subtotal - discount + tax + shipping,
    }
