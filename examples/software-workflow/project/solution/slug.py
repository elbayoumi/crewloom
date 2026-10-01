"""Unicode-aware slugs without third-party dependencies."""
import unicodedata


def slugify(value):
    if not isinstance(value, str):
        raise TypeError('slugify requires a string')
    normalized = unicodedata.normalize('NFKC', value).casefold()
    words = []
    current = []
    for character in normalized:
        if character.isalpha() or character.isdecimal():
            current.append(character)
        elif current:
            words.append(''.join(current)); current = []
    if current:
        words.append(''.join(current))
    return '-'.join(words)
