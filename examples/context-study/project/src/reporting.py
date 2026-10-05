"""CSV rendering for the finance export job.

The export owns its own formatting and deliberately imports none of the billing
modules, so a reporting change can never alter how money is parsed or rounded.
Inputs reach this module already formatted; it only arranges columns.
"""
import csv
import io

COLUMNS = ('currency', 'category', 'total')


def rows(entries):
    """Yield already-formatted entry rows in the order they were given."""
    for entry in entries:
        yield tuple(str(entry.get(column, '')) for column in COLUMNS)


def to_csv(entries):
    """Render entries as CSV text with a header row."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(COLUMNS)
    writer.writerows(rows(entries))
    return buffer.getvalue()


def to_markdown(entries):
    """Render the same entries as a Markdown table for review comments."""
    lines = ['| ' + ' | '.join(COLUMNS) + ' |',
             '| ' + ' | '.join(['---'] * len(COLUMNS)) + ' |']
    for row in rows(entries):
        lines.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(lines)