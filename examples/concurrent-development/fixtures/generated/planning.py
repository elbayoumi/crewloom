"""Deterministic priority planning over a small dependency graph.

The plan is a pure function of the task list, so two runs on two machines produce the same
order. Three rules decide everything:

1. ``depth`` first — a task is scheduled only after everything it depends on, so priority can
   never promote a task above work it is waiting for;
2. ``-priority`` next — inside one depth, the higher priority runs first and a missing
   priority is zero;
3. ``id`` last — ties break lexically, never by input order.

Waves are that ordering chunked by a capacity, so a wave never mixes depths and never
exceeds the capacity. A cycle is refused by name instead of being silently dropped.
"""
from scheduling_support import check_dependencies, check_id, check_priority

CAPACITY_MIN = 1
CAPACITY_MAX = 8
DEFAULT_CAPACITY = 2


def check_capacity(value):
    """An explicit integer capacity; an omitted value uses the documented default."""
    if value is None:
        return DEFAULT_CAPACITY
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('capacity must be an integer from ' + str(CAPACITY_MIN) + ' to '
                         + str(CAPACITY_MAX))
    if not CAPACITY_MIN <= value <= CAPACITY_MAX:
        raise ValueError('capacity must be an integer from ' + str(CAPACITY_MIN) + ' to '
                         + str(CAPACITY_MAX))
    return value


def checked_tasks(tasks):
    """Validated task records in input order; every failure is refused before any planning."""
    if not isinstance(tasks, list):
        raise ValueError('tasks must be a list of task objects')
    records = []
    seen = set()
    for index, record in enumerate(tasks):
        if not isinstance(record, dict):
            raise ValueError('task ' + str(index) + ' must be an object')
        ident = check_id(record.get('id'), 'task ' + str(index) + ' id')
        if ident in seen:
            raise ValueError('task ' + ident + ' is declared twice')
        seen.add(ident)
        depends_on = check_dependencies(record.get('depends_on'), ident + ' depends_on')
        for dependency in depends_on:
            if dependency == ident:
                raise ValueError('task ' + ident + ' depends on itself')
        records.append({'id': ident, 'depends_on': list(depends_on),
                        'priority': check_priority(record.get('priority'), ident + ' priority')})
    for record in records:
        for dependency in record['depends_on']:
            if dependency not in seen:
                raise ValueError('task ' + record['id'] + ' depends on unknown task '
                                 + dependency)
    return records


def detect_cycle(tasks):
    """The ids on one dependency cycle in visit order, or an empty list when the graph is sound.

    Three-colour depth-first search, so the answer is one concrete cycle rather than every
    task that happens to be downstream of one.
    """
    records = checked_tasks(tasks)
    outgoing = {record['id']: [item for item in record['depends_on']
                               if any(other['id'] == item for other in records)] for record in records}
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {ident: WHITE for ident in outgoing}
    path = []

    def visit(ident):
        colour[ident] = GREY
        path.append(ident)
        for dependency in sorted(outgoing[ident]):
            if colour[dependency] == GREY:
                return path[path.index(dependency):] + [dependency]
            if colour[dependency] == WHITE:
                found = visit(dependency)
                if found:
                    return found
        path.pop()
        colour[ident] = BLACK
        return None

    for ident in sorted(outgoing):
        if colour[ident] == WHITE:
            found = visit(ident)
            if found:
                return found
    return []


def depths(tasks):
    """Map every task id to its dependency depth; a cycle is refused with the ids involved."""
    records = checked_tasks(tasks)
    cycle = detect_cycle(records)
    if cycle:
        raise ValueError('dependency cycle: ' + ' -> '.join(cycle))
    known = {record['id']: record for record in records}
    result = {}

    def resolve(ident):
        if ident in result:
            return result[ident]
        parents = known[ident]['depends_on']
        result[ident] = 1 + max([resolve(item) for item in parents], default=0)
        return result[ident]

    for record in records:
        resolve(record['id'])
    return result


def schedule(tasks, capacity=None):
    """The whole plan: capacity, dependency-first order, depth map and capacity waves."""
    records = checked_tasks(tasks)
    limit = check_capacity(capacity)
    levels = depths(records)
    ordered = sorted(records, key=lambda record: (levels[record['id']], -record['priority'],
                                                  record['id']))
    order = [record['id'] for record in ordered]
    waves = [order[index:index + limit] for index in range(0, len(order), limit)]
    latest = max(levels.values()) if levels else 0
    return {'capacity': limit, 'order': order, 'waves': waves,
            'depths': {ident: levels[ident] for ident in sorted(levels)},
            'latest_tasks': [ident for ident in order if levels[ident] == latest],
            'priority_total': sum(record['priority'] for record in records),
            'task_count': len(records)}