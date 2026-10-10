"""Grader-only reference; never supplied in a model prompt."""
import re


def reconcile(events):
    if not isinstance(events, list):
        raise ValueError('Invalid events')
    seen, latest = {}, {}
    for item in events:
        if not isinstance(item, dict) or set(item) != {'project_id', 'task_id', 'seq', 'state'}:
            raise ValueError('Invalid event')
        for key in ('project_id', 'task_id'):
            if not isinstance(item[key], str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', item[key], re.ASCII):
                raise ValueError('Invalid identity')
        if type(item['seq']) is not int or item['seq'] < 0 or item['state'] not in ('queued', 'running', 'verified', 'failed', 'cancelled'):
            raise ValueError('Invalid sequence or state')
        key = (item['project_id'], item['task_id'])
        version = (*key, item['seq'])
        if version in seen and seen[version] != item['state']:
            raise ValueError('Conflicting duplicate')
        seen[version] = item['state']
        if key not in latest or item['seq'] > latest[key]['seq']:
            latest[key] = dict(item)
    return [latest[key] for key in sorted(latest)]
