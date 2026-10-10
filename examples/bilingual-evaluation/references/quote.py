"""Grader-only reference; never supplied in a model prompt."""
def quote(order):
    if not isinstance(order, dict) or set(order) - {'lines', 'discount_bps', 'tax_bps', 'shipping_cents'}:
        raise ValueError('Invalid order')
    lines = order.get('lines')
    if not isinstance(lines, list) or not lines:
        raise ValueError('Invalid lines')
    subtotal = 0
    for item in lines:
        if not isinstance(item, dict) or set(item) != {'price_cents', 'quantity'}:
            raise ValueError('Invalid line')
        price, quantity = item['price_cents'], item['quantity']
        if type(price) is not int or price < 0 or type(quantity) is not int or quantity < 1:
            raise ValueError('Invalid amount')
        subtotal += price * quantity
    discount, tax, shipping = (order.get(k, 0) for k in ('discount_bps', 'tax_bps', 'shipping_cents'))
    if any(type(n) is not int or n < 0 for n in (discount, tax, shipping)) or discount > 10000 or tax > 10000:
        raise ValueError('Invalid rates')
    discount = (subtotal * discount + 5000) // 10000
    tax = ((subtotal - discount) * tax + 5000) // 10000
    return {'subtotal_cents': subtotal, 'discount_cents': discount, 'tax_cents': tax,
            'total_cents': subtotal - discount + tax + shipping}
