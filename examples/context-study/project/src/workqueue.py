"""The worker pool's first-in-first-out run queue.

It predates ``src/scheduler.py``: runs arrive already ordered by the caller, so
this module only hands the next run to a free worker and remembers what it has
handed out. It is the neighbouring module a scheduler change is most likely to
touch, which is exactly why it stays in the fixture.
"""
from collections import deque

from src.scheduling import check_id


class RunQueue:
    """First-in-first-out queue of named runs."""

    def __init__(self):
        self._pending = deque()

    def submit(self, ident):
        """Queue one run and report how many are waiting."""
        check_id(ident, 'run')
        self._pending.append(ident)
        return len(self._pending)

    def next_run(self):
        """Hand out the oldest waiting run, or None when the queue is empty."""
        if not self._pending:
            return None
        return self._pending.popleft()

    def waiting(self):
        """The queued runs in order, for the status endpoint."""
        return list(self._pending)

    def forget(self, ident):
        """Drop every queued copy of one run; returns how many were removed."""
        keep = [item for item in self._pending if item != ident]
        removed = len(self._pending) - len(keep)
        self._pending = deque(keep)
        return removed