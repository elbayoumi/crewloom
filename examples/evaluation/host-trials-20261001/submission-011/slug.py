import unicodedata


def slugify(value):
    """Normalize a string into a slug of Unicode letters and decimal digits."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    value = unicodedata.normalize("NFKC", value).casefold()
    result = []
    separator_pending = False

    for char in value:
        category = unicodedata.category(char)
        if category.startswith("L") or category == "Nd":
            if separator_pending and result:
                result.append("-")
            result.append(char)
            separator_pending = False
        else:
            separator_pending = True

    return "".join(result)
