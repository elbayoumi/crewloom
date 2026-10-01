# Unicode slug feature

Implement `src/slug.py` with `slugify(value)` using the Python standard library.
Reject non-strings with TypeError. Apply Unicode NFKC then casefold. Preserve
Unicode letters and decimal digits. Collapse runs of all other characters to
one hyphen, trim edge hyphens, and return an empty string for empty/punctuation input.
Do not claim executed checks: the next workflow step verifies the artifact.
