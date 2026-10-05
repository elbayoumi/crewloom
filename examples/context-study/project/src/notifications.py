"""Operator notification text.

Delivery is somebody else's problem; this module only builds the message. It
must never import project data, because a recipient can sit outside the team and
a notification is the one artifact that leaves the project by design.
"""

CHANNELS = ('email', 'pager', 'chat')
MAX_LINES = 40


def heading(channel, subject):
    """The subject line for one notification channel."""
    if channel not in CHANNELS:
        raise ValueError('unknown notification channel: ' + str(channel))
    text = str(subject).strip()
    return text or 'Crewloom notification'


def body(lines, limit=MAX_LINES):
    """Join the non-empty message lines, bounded to the channel's line budget."""
    kept = [str(line).strip() for line in lines if str(line).strip()][:limit]
    return '\n'.join(kept)


def render(channel, subject, lines):
    """One complete message: heading, blank line, then the bounded body."""
    return heading(channel, subject) + '\n\n' + body(lines)