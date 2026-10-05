"""Task identifier and field validation shared by the scheduling modules.

The wire format is validated here once so the ordering code can assume every
task already satisfies it, and so an invalid task is refused before any partial
plan exists. Validation never mutates its argument: a caller's list is read, and
a fresh normalized record is returned instead.
"""
import re

TASK_ID = re.compile(r'[a-z][a-z0-9-]{0,31}\Z')
PRIORITY_MIN = -9
PRIORITY_MAX = 9


def check_id(value, field='id'):
    """One valid task identifier: lowercase ASCII, at most 32 characters."""
    if not isinstance(value, str) or not TASK_ID.match(value):
        raise ValueError(field + ' must match [a-z][a-z0-9-]{0,31}')
    return value


def check_priority(value, field='priority'):
    """A bounded integer priority; an omitted priority is zero.

    A boolean is an integer in Python but never a priority here, so it is
    refused rather than silently treated as 1.
    """
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(field + ' must be an integer from ' + str(PRIORITY_MIN) +
                         ' to ' + str(PRIORITY_MAX))
    if not PRIORITY_MIN <= value <= PRIORITY_MAX:
        raise ValueError(field + ' must be an integer from ' + str(PRIORITY_MIN) +
                         ' to ' + str(PRIORITY_MAX))
    return value


def check_dependencies(value, field='depends_on'):
    """Unique identifier strings; an omitted value means no dependencies."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(field + ' must be a list of task identifiers')
    checked = []
    for item in value:
        check_id(item, field)
        if item in checked:
            raise ValueError(field + ' repeats ' + item)
        checked.append(item)
    return tuple(checked)


def check_task(record, field='task'):
    """Validate one task record and return its normalized fields.

    Unknown extra fields are ignored rather than refused: the scheduler only
    needs the three declared ones, and a newer producer may add metadata.
    """
    if not isinstance(record, dict):
        raise ValueError(field + ' must be an object')
    if 'id' not in record:
        raise ValueError('task needs an id')
    return {'id': check_id(record['id']),
            'depends_on': check_dependencies(record.get('depends_on')),
            'priority': check_priority(record.get('priority'))}