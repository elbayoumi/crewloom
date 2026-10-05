"""Deterministic topological task order."""
from src.scheduling import check_task


def plan(tasks):
    """Order every task after its dependencies, highest priority first."""
    if not isinstance(tasks, list):
        raise TypeError('tasks must be a list')
    normalized = []
    identifiers = set()
    for record in tasks:
        item = check_task(record)
        if item['id'] in identifiers:
            raise ValueError('duplicate task id: ' + item['id'])
        identifiers.add(item['id'])
        normalized.append(item)
    for item in normalized:
        for dependency in item['depends_on']:
            if dependency not in identifiers:
                raise ValueError('unknown dependency: ' + dependency)
            if dependency == item['id']:
                raise ValueError('task depends on itself: ' + item['id'])
    order = []
    done = set()
    remaining = {item['id']: item for item in normalized}
    while remaining:
        ready = [name for name, item in remaining.items()
                 if all(dependency in done for dependency in item['depends_on'])]
        if not ready:
            raise ValueError('dependency cycle')
        chosen = min(ready, key=lambda name: (-remaining[name]['priority'], name))
        order.append(chosen)
        done.add(chosen)
        del remaining[chosen]
    return order
