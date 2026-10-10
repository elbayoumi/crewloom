import re


_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
_FIELDS = {"project_id", "task_id", "seq", "state"}
_STATES = ("queued", "running", "verified", "failed", "cancelled")


def reconcile(events):
    """Return the latest event per project/task, rejecting invalid or conflicting events."""
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    seen = {}
    latest = {}
    for event in events:
        if not isinstance(event, dict) or set(event) != _FIELDS:
            raise ValueError("each event must contain exactly project_id, task_id, seq, state")

        project_id = event["project_id"]
        task_id = event["task_id"]
        seq = event["seq"]
        state = event["state"]

        for identifier in (project_id, task_id):
            if not isinstance(identifier, str) or _ID_PATTERN.fullmatch(identifier) is None:
                raise ValueError("invalid project_id or task_id")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            raise ValueError("seq must be a nonnegative integer, excluding bool")
        if not isinstance(state, str) or state not in _STATES:
            raise ValueError("invalid state")

        version_key = (project_id, task_id, seq)
        if version_key in seen and seen[version_key] != state:
            raise ValueError("conflicting states for the same project, task, and seq")
        seen[version_key] = state

        task_key = (project_id, task_id)
        if task_key not in latest or seq > latest[task_key]["seq"]:
            latest[task_key] = {
                "project_id": project_id,
                "task_id": task_id,
                "seq": seq,
                "state": state,
            }

    return [latest[key] for key in sorted(latest)]
