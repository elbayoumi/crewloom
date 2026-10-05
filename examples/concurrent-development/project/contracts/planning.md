# Contract: `src/planning.py`

Write exactly one module at `src/planning.py`. Standard library only. It is imported by
`src/report.py`, so its public names are the contract, not its internals.

## Inputs it must rely on

`src/scheduling_support.py` is already in the project and is reused, not reimplemented:

- `check_id(value, field='id') -> str` — lowercase ASCII task id, `[a-z][a-z0-9-]{0,31}`;
- `check_priority(value, field='priority') -> int` — bounded integer, an omitted priority is
  `0`, a `bool` is refused;
- `check_dependencies(value, field='depends_on') -> tuple` — unique ids, an omitted value is
  `()`.

## Public surface

```python
CAPACITY_MIN = 1
CAPACITY_MAX = 8
DEFAULT_CAPACITY = 2

def check_capacity(value) -> int       # explicit int; an omitted value uses DEFAULT_CAPACITY
def checked_tasks(tasks) -> list        # validated {'id','depends_on','priority'} in input order
def detect_cycle(tasks) -> list        # ids on one cycle in visit order, [] when sound
def depths(tasks) -> dict              # id -> dependency depth; a cycle raises ValueError
def schedule(tasks, capacity=None) -> dict
```

## Ordering

The plan is a pure function of the task list. Sort by, in order:

1. `depth` ascending — a task is planned only after everything it depends on, so priority
   can never promote a task above work it waits for;
2. `-priority` descending — higher priority first inside one depth, `0` for an omitted one;
3. `id` ascending — ties break lexically, never by input order.

Depth is `1 + max(depth(dependencies))`, and a task without dependencies has depth `1`.

## Waves

`waves` is that ordering chunked by capacity: consecutive slices of at most `capacity` ids, in
order. A chunk can contain consecutive tasks of different depths; these are display batches of an ordered plan, and do not authorize concurrent execution of dependencies. Each chunk never exceeds the capacity. `capacity` is validated
before use and an out-of-range or boolean capacity raises `ValueError`.

## `schedule` output

```python
{'capacity': int, 'order': [ids in planned order], 'waves': [[ids], ...],
 'depths': {id: int, ...},           # sorted by key
 'latest_tasks': [ids at maximum depth, in planned order],
 'priority_total': int, 'task_count': int}
```

## Refusals, all `ValueError`

- `tasks` is not a list, or a task is not an object, or a task has no valid id;
- a duplicate task id;
- a `depends_on` that repeats an id, names an unknown task, or names the task itself;
- a boolean or non-integer priority, or a priority outside `-9..9`;
- a dependency cycle, refused with the ids in visit order so the cycle can be read directly;
- an empty task list is valid and yields `order == []`, `waves == []`, `task_count == 0`.

Two calls with equal input must return equal output; no set iteration order, clock, locale or
environment may reach the result.