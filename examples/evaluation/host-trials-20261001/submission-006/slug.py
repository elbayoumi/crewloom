import unicodedata


def slugify(value: str) -> str:
    """Normalize text into a slug containing Unicode letters and decimal digits."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    value = unicodedata.normalize("NFKC", value).casefold()
    result = []
    for char in value:
        category = unicodedata.category(char)
        if category.startswith("L") or category == "Nd":
            result.append(char)
        elif result and result[-1] != "-":
            result.append("-")

    return "".join(result).rstrip("-")
