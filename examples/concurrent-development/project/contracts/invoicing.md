# Contract: `src/billing.py`

Write exactly one module at `src/billing.py`. Standard library only. It is imported by
`src/report.py`, so its public names are the contract, not its internals.

## Inputs it must rely on

`src/money.py` is already in the project and is reused, not reimplemented:

- `parse_amount(value, field='amount') -> Decimal` — exact decimal string parsing. Floats,
  booleans, `NaN` and `Infinity` raise `ValueError`.
- `quantize(amount, places=2) -> Decimal` — one rounding decision, `ROUND_HALF_EVEN`.
- `format_amount(amount, places=2) -> str` — fixed-scale rendering, `format(value, 'f')`.
- `PLACES` is `2`.

## Public surface

```python
CURRENCIES = ('EUR', 'SAR', 'USD')
CATEGORIES = ('hardware', 'refund', 'services', 'subscription')
LANGUAGES = ('ar', 'en')
MAX_QUANTITY = 10000
ROUNDING_POLICY = str
SECTION_TITLES = {'en': {...}, 'ar': {...}}   # keys: net, tax, gross, per_line_tax

def check_currency(value) -> str      # ValueError unless value is exactly one supported code
def check_category(value) -> str      # ValueError unless value is exactly one supported category
def check_language(value) -> str      # ValueError unless value is 'ar' or 'en'
def line_amounts(line, index) -> dict # exact unrounded Decimals: net, tax, gross
def compute_invoice(invoice) -> dict
```

`line_amounts` returns `currency`, `category`, `quantity`, `unit_price`, `tax_rate`, `net`,
`tax` and `gross` as `Decimal`, unrounded.

## Validation

- `line` must be an object; `quantity` an `int` in `1..MAX_QUANTITY` (a `bool` is refused);
- `unit_price` and `tax_rate` go through `parse_amount`, so a JSON float or the string
  `'NaN'` is refused; `unit_price` must be positive; `tax_rate` is quantized to 4 decimal
  places and must be within `0..100`;
- `category == 'refund'` negates an otherwise positive line, so a refund reduces the group
  total instead of being signed inside `quantity`;
- `description_en` and `description_ar` must both be nonempty strings after stripping whitespace; missing or empty descriptions raise `ValueError` naming that field;
- every error message names the offending line index and field;
- `compute_invoice` refuses a missing/empty `lines` list and a missing `invoice_id`.

## Rounding semantics, stated exactly

For each line: `tax = net * tax_rate.scaleb(-2)` and `gross = net + tax`, both **unrounded**.
For each currency group, totals are the `quantize`/`format_amount` of the **sum of the
unrounded values**, so there is exactly one rounding decision per group total.

`by_currency[currency]['per_line_tax']` is the sum of the *per-line* quantized taxes, reported
next to the group tax so the difference between "round once per group" and "round every line"
is visible in the output rather than hidden.

## `compute_invoice` output

```python
{'invoice_id': str, 'language': 'ar'|'en', 'titles': {...}, 'rounding': ROUNDING_POLICY,
 'lines': [{'index': 1, 'description_en': str, 'description_ar': str, 'label': str,
            'currency': str, 'category': str, 'quantity': int,
            'net': str, 'tax': str, 'gross': str}, ...],
 'by_currency': {'EUR': {'net': str, 'tax': str, 'gross': str, 'per_line_tax': str}, ...},
 'single_currency': bool, 'currencies': [sorted codes]}
```

- amounts are fixed-scale decimal **strings** (`format_amount`), never floats;
- `currencies` and `by_currency` keys are sorted, so two runs agree byte for byte;
- `lines.label` is `description_en` or `description_ar` according to the invoice `language`,
  and both descriptions are always present;
- a mixed-currency invoice is valid and simply has no single total: `single_currency` is
  `False` and each currency carries its own totals;
- `compute_invoice` never mutates the invoice it was given.