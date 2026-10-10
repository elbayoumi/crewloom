"""حساب عرض السعر بأعداد صحيحة دون تعديل المدخل."""


def _integer(value, field, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{field} is out of range")
    return value


def quote(order):
    if not isinstance(order, dict):
        raise ValueError("order must be a dictionary")

    allowed = {"lines", "discount_bps", "tax_bps", "shipping_cents"}
    if "lines" not in order or set(order) - allowed:
        raise ValueError("order must contain lines and no unknown fields")

    lines = order["lines"]
    if not isinstance(lines, list) or not lines:
        raise ValueError("lines must be a nonempty list")

    discount_bps = _integer(order.get("discount_bps", 0), "discount_bps", maximum=10000)
    tax_bps = _integer(order.get("tax_bps", 0), "tax_bps", maximum=10000)
    shipping = _integer(order.get("shipping_cents", 0), "shipping_cents")

    subtotal = 0
    for line in lines:
        if not isinstance(line, dict) or set(line) != {"price_cents", "quantity"}:
            raise ValueError("each line must contain exactly price_cents and quantity")
        price = _integer(line["price_cents"], "price_cents")
        quantity = _integer(line["quantity"], "quantity", minimum=1)
        subtotal += price * quantity

    discount = (subtotal * discount_bps + 5000) // 10000
    tax = ((subtotal - discount) * tax_bps + 5000) // 10000
    return {
        "subtotal_cents": subtotal,
        "discount_cents": discount,
        "tax_cents": tax,
        "total_cents": subtotal - discount + tax + shipping,
    }
