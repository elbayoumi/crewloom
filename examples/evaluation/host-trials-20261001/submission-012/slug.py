import unicodedata


def slugify(value: str) -> str:
    """Normalize text into a slug preserving Unicode letters and decimal digits."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    normalized = unicodedata.normalize("NFKC", value).casefold()
    result = []
    separator_pending = False

    for character in normalized:
        category = unicodedata.category(character)
        if category.startswith("L") or category == "Nd":
            if separator_pending and result:
                result.append("-")
            result.append(character)
            separator_pending = False
        else:
            separator_pending = True

    return "".join(result)
