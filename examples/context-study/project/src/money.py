"""Exact decimal money parsing and formatting shared by the billing modules.

Provider exports carry amounts as decimal strings, sometimes in exponent
notation. They are parsed here once, so no billing module ever touches a binary
float and no module has to reinvent the "is this a finite amount" rule.

Every amount in this package is a :class:`decimal.Decimal`. Floats, booleans,
``NaN`` and ``Infinity`` are refused at the boundary, because a single float
that reaches a running sum silently destroys every later total.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext

DECIMAL_TEXT = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z')
PLACES = 2
PRECISION = 34


def parse_amount(value, field='amount'):
    """Parse one finite decimal amount, or refuse the value with ValueError.

    Exponents are accepted because providers emit them; surrounding whitespace is
    ignored because exports are padded. Nothing else is coerced: a caller that
    wants a different tolerance has to say so explicitly.
    """
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(field + ' must be a decimal string')
    text = value.strip()
    if not DECIMAL_TEXT.match(text):
        raise ValueError(field + ' must be a finite decimal string')
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError(field + ' must be a finite decimal string') from None
    if not amount.is_finite():
        raise ValueError(field + ' must be a finite decimal string')
    return amount


def total_of(amounts):
    """Add exact amounts without rounding anything in between."""
    running = Decimal(0)
    for amount in amounts:
        running += amount
    return running


def quantize(amount, places=PLACES):
    """Round one finished group sum to the currency scale, ROUND_HALF_EVEN.

    Call this once per group and never per record: rounding each record first is
    how a 0.005 plus 0.005 invoice becomes 0.00 instead of 0.01.
    """
    with localcontext() as context:
        context.prec = PRECISION
        return amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def format_amount(amount, places=PLACES):
    """Render a quantized amount with a fixed number of decimals."""
    value = quantize(amount, places)
    if not value:
        value = abs(value)
    return format(value, 'f')