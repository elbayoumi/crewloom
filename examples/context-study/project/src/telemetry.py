"""Process-local counters exported by the worker entry points.

Nothing in the billing, scheduling or path modules reads these. The dashboards
poll them out of band, which is why this module may never grow a dependency on
project data: a counter that raised during a poll would take the metrics with
it.
"""
import threading

_LOCK = threading.Lock()
_COUNTERS = {}


def increment(name, amount=1):
    """Add to one counter and return its new value."""
    if not isinstance(name, str) or not name:
        raise ValueError('counter name must be a nonempty string')
    with _LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + amount
        return _COUNTERS[name]


def snapshot():
    """A copy of every counter, safe to serialise."""
    with _LOCK:
        return dict(_COUNTERS)


def reset():
    """Drop every counter; used between test runs only."""
    with _LOCK:
        _COUNTERS.clear()