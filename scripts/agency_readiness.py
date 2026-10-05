#!/usr/bin/env python3
"""Read-only rollout readiness for one explicitly selected registered agency project.

The reporter answers one narrow question: does the existing agency project-control ledger
register this canonical project root under this exact ID, and does the state that ledger
records still describe the files on disk now? It reuses
`project_binding.validate_agency_registry` and `project_binding.agency_registry` as the only
registry authority, so the ledger schema, its statuses and its path rules stay exactly one
implementation and this tool keeps no second client list and no second contract.

Read-only is a property of the default invocation, not a promise in prose. No file,
directory, cache, `.crewloom`, `AGENTS.md`, project configuration, local binding or
reconciliation state is created; no Git, network or host command runs; and the mutating
external agency validator the project lifecycle can run is deliberately not run here. The
only optional write is one explicit report file inside the `.crewloom/readiness` namespace
this reporter owns in the selected project, and only after the same explicit ID and root
resolve to a valid registration. A `needs_reconciliation` entry is reported as recorded and
never improved.

A `ready` verdict is scoped to registration and evidence freshness. It does not verify
delivery, host configuration or agent capability.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import crewloom_resources as resources
import project_binding as pb
import workflow as w

TOOL = 'agency-readiness'
MODE = 'read-only'
REPORT_SCHEMA_VERSION = 1
OUTCOMES = ('ready', 'needs_reconciliation', 'not_ready', 'blocked', 'error')
PROBLEM_KINDS = ('schema', 'identity', 'status', 'path', 'hash', 'ownership', 'timestamp',
                 'stale', 'evidence', 'missing', 'setup', 'blocked')
DEFAULT_EVIDENCE_AGE_SECONDS = 2592000
MIN_EVIDENCE_AGE_SECONDS = 0
MAX_EVIDENCE_AGE_SECONDS = 31536000
# A recorded timestamp this far ahead of the clock cannot be an honest observation, but a
# small skew is normal on any host whose clock was adjusted between recording and reading.
FUTURE_SKEW_SECONDS = 60
MAX_PROBLEMS = 200
MAX_REPORT_BYTES = 262144
RUNTIME_DIRECTORY = '.crewloom'
# The reporter owns exactly one directory inside the project runtime. Restricting the write to
# its own namespace is what keeps a readiness report from ever replacing runtime authority such
# as the local binding, the reviewer registry, a task reservation or controller state.
REPORT_NAMESPACE = 'readiness'
SUGGESTED_REPORT_PATH = RUNTIME_DIRECTORY + '/' + REPORT_NAMESPACE + '/report.json'
EXIT_READY = 0
EXIT_NOT_READY = 2
LANGUAGES = ('en', 'ar')

SCOPE = (
    'the explicit registry file carries the exact ledger schema and has no duplicate or '
    'unknown entry fields',
    'exactly one registered entry resolves to this explicit canonical project root under '
    'this explicit project ID',
    'recorded verification and observation timestamps are parseable, timezone-aware and '
    'inside the explicit age limit measured against the real UTC clock',
    'the recorded state evidence is a real nonempty file inside its own active_dir whose '
    'current digest still equals the recorded digest',
    'the project carries a valid portable configuration and local binding for the same '
    'identity',
)
LIMITATIONS = (
    'ready covers registration and evidence freshness only; delivery, host configuration, '
    'installed agents and agent capability are not verified here',
    'a matching digest proves the evidence file is unchanged since it was observed, not '
    'that its contents are true',
    'this reporter never reconciles evidence, never changes control_status and never writes '
    'client state, a binding, a project configuration or a ledger',
    'the mutating external agency validator the project lifecycle can run is not run here, '
    'so a ledger that only its own validator accepts is reported as checked, not as passed',
    'missing project configuration or binding is reported as required setup; this reporter '
    'never bootstraps one',
)
LABELS = {
    'en': {'ready': 'Ready within registration and evidence scope',
           'needs_reconciliation': 'The ledger records this project as needing reconciliation',
           'not_ready': 'Not ready; see the reported problems',
           'blocked': 'Blocked; the registration could not be checked',
           'note': 'Read-only report. No file, configuration or ledger entry was created or changed.'},
    'ar': {'ready': 'جاهز ضمن نطاق التسجيل والأدلة',
           'needs_reconciliation': 'يسجل سجل التحكم بالمشاريع هذا المشروع على أنه يحتاج إلى مطابقة',
           'not_ready': 'غير جاهز؛ راجع المشاكل المسجلة',
           'blocked': 'موقوف؛ تعذر التحقق من التسجيل',
           'note': 'تقرير للقراءة فقط. لم يتم إنشاء أو تعديل أي ملف أو إعداد أو قيد في السجل.'},
}
# The adapter's own messages are reused verbatim, so they are classified by their subject
# rather than rewritten. Order matters: the most specific subject decides the kind.
ADAPTER_PROBLEM_KINDS = (
    ('schema_version', 'schema'),
    ('unknown fields', 'schema'),
    ('unreadable', 'schema'),
    ('projects must be', 'schema'),
    ('must be an object', 'schema'),
    ('must be a nonempty list', 'schema'),
    ('file not found', 'path'),
    ('escapes the agency workspace root', 'path'),
    ('outside its active_dir', 'path'),
    ('context_snapshot', 'path'),
    ('active_dir', 'path'),
    ('relative path', 'path'),
    ('delivery_owner', 'ownership'),
    ('next_action.owner', 'ownership'),
    ('installed role', 'ownership'),
    ('control_status', 'status'),
    ('last_verified_at', 'timestamp'),
    ('state_evidence.sha256', 'hash'),
    ('state_evidence.path', 'path'),
    ('changed since observation', 'hash'),
    ('state_evidence.source_type', 'evidence'),
    ('observed_at', 'timestamp'),
    ('state_evidence: required', 'missing'),
    ('unique lowercase identifier', 'identity'),
    ('.id', 'identity'),
    ('is empty', 'missing'),
    ('required', 'missing'),
)


def _limit(value):
    """The evidence age limit is one explicit bounded integer, never a silent default guess."""
    if type(value) is not int or not MIN_EVIDENCE_AGE_SECONDS <= value <= MAX_EVIDENCE_AGE_SECONDS:
        raise ValueError('Evidence age limit must be an integer from ' + str(MIN_EVIDENCE_AGE_SECONDS)
                         + ' to ' + str(MAX_EVIDENCE_AGE_SECONDS) + ' seconds')
    return value


def _clock(value):
    """Real current UTC, or the aware instant a caller injected for a deterministic check."""
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('An injected clock must be a timezone-aware datetime')
    return value.astimezone(timezone.utc)


def _parse(value):
    """Return (aware datetime or None, parseable) for one recorded timestamp."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None, False
    aware = parsed.tzinfo is not None and parsed.utcoffset() is not None
    return (parsed.astimezone(timezone.utc) if aware else None), True


def _problem(payload, kind, field, detail, blocking=False):
    """Record one reason. The list is bounded, and a cut list says so instead of implying completeness."""
    if kind not in PROBLEM_KINDS:
        raise ValueError('Unknown problem kind: ' + str(kind))
    if len(payload['problems']) < MAX_PROBLEMS:
        payload['problems'].append({'kind': kind, 'field': field, 'detail': detail,
                                    'blocking': bool(blocking)})
        if blocking:
            payload['blocked_reasons'].append(detail)
    else:
        payload['problems_truncated'] = True


def _recorded(value, clock, limit, field, required=True):
    """Report one recorded timestamp honestly: unparseable, naive, stale and future stay distinct."""
    parsed, parseable = _parse(value)
    record = {'field': field, 'recorded': value if isinstance(value, str) else None,
              'parseable': parseable, 'timezone_aware': parsed is not None,
              'required': bool(required), 'age_seconds': None, 'within_limit': None,
              'in_future': False}
    if parsed is not None:
        age = (clock - parsed).total_seconds()
        record['age_seconds'] = age
        record['in_future'] = age < -FUTURE_SKEW_SECONDS
        record['within_limit'] = (not record['in_future']) and age <= limit
    return record


def _check_timestamp(payload, record, label):
    """One recorded timestamp, its parseability, its offset and its age against the explicit limit."""
    if record['recorded'] is None:
        if record['required']:
            _problem(payload, 'missing', record['field'],
                     label + ' is absent; an operational status needs a recorded timestamp')
        return
    if not record['parseable']:
        _problem(payload, 'timestamp', record['field'],
                 label + ' is not a parseable ISO-8601 timestamp: ' + repr(record['recorded']))
        return
    if not record['timezone_aware']:
        _problem(payload, 'timestamp', record['field'],
                 label + ' has no timezone offset: ' + repr(record['recorded']))
        return
    if record['in_future']:
        _problem(payload, 'timestamp', record['field'],
                 label + ' is in the future relative to the checked clock: ' + repr(record['recorded']))
        return
    if not record['within_limit']:
        _problem(payload, 'stale', record['field'],
                 label + ' is older than the explicit evidence age limit of '
                 + str(payload['evidence_age_limit_seconds']) + ' seconds (age '
                 + str(int(record['age_seconds'])) + 's)')


def _no_links(base, relative, label):
    """Refuse a symlinked component before anything resolves it."""
    current = base
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(label + ' may not use symlinked components: ' + str(relative))
    return current


def _inside(base, relative):
    """Resolve one recorded agency-relative path, refusing traversal and symlinked components."""
    if not isinstance(relative, str) or not relative.strip() or relative.startswith('/') or '\0' in relative:
        return None, 'must be a non-empty relative path inside the agency workspace root'
    try:
        _no_links(base, relative, 'A recorded agency path')
    except ValueError as exc:
        return None, str(exc)
    resolved = (base / relative).resolve()
    if resolved == base or not resolved.is_relative_to(base):
        return None, 'resolves outside the explicit agency workspace root'
    return resolved, None


def _agency_paths(agency_root, registry):
    """The explicit agency workspace root and registry file, resolved with the adapter's own rules."""
    if isinstance(agency_root, Path):
        agency_root = str(agency_root)
    if not isinstance(agency_root, str) or not agency_root.strip():
        raise ValueError('Explicit agency workspace root is required; it is never inferred from '
                         'the registry path, the project root or the working directory')
    base = Path(agency_root).resolve()
    if not base.is_dir():
        raise ValueError('Agency workspace root does not exist: ' + agency_root)
    if isinstance(registry, Path):
        candidate = registry
    elif isinstance(registry, str) and registry.strip():
        candidate = Path(registry.strip())
    else:
        raise ValueError('Explicit agency project-control registry path is required')
    if candidate.is_absolute():
        anchor = Path(candidate.anchor)
        relative = candidate.relative_to(anchor)
    else:
        anchor, relative = base, candidate
    _no_links(anchor, relative, 'The agency registry path')
    path = (anchor / relative).resolve()
    if path == base or not path.is_relative_to(base):
        raise ValueError('Agency registry path escapes the explicit agency workspace root')
    if path.exists():
        if not path.is_file():
            raise ValueError('Agency registry must be a regular file: ' + str(path))
        if path.stat().st_nlink != 1:
            raise ValueError('Agency registry must not be a hardlink: ' + str(path))
    return base, path


def _payload(project_id, limit, clock, language):
    return {'schema_version': REPORT_SCHEMA_VERSION, 'tool': TOOL, 'mode': MODE, 'outcome': 'blocked',
            'ready': False, 'project_id': project_id, 'project_root': None, 'agency_root': None,
            'registry_path': None, 'checked_at': clock.isoformat(timespec='seconds'),
            'evidence_age_limit_seconds': limit,
            'registry': {'present': False, 'sha256': None, 'matched_entries': 0, 'matched_ids': []},
            'control_status': None, 'evidence_only': None,
            'ownership': {'delivery_owner': None, 'next_action_owner': None},
            'context_snapshot': {'recorded': None, 'resolved': None, 'present': False, 'size_bytes': None},
            'timestamps': {'last_verified_at': _recorded(None, clock, limit, 'last_verified_at', False),
                           'state_evidence.observed_at': _recorded(None, clock, limit,
                                                                    'state_evidence.observed_at', False)},
            'current_evidence': {'recorded': None, 'resolved': None, 'present': False, 'is_file': False,
                                 'size_bytes': None, 'recorded_sha256': None, 'current_sha256': None,
                                 'digest_matches': None, 'source_type': None,
                                 'source_type_accepted': None, 'symlinked': False, 'hardlinks': None},
            'setup': {'config_path': pb.CONFIG_NAME, 'config_present': False, 'config_project_id': None,
                      'binding_path': pb.BINDING_RELATIVE, 'binding_present': False,
                      'binding_project_id': None, 'enrolled': False},
            'missing_fields': [], 'problems': [], 'problems_truncated': False, 'problem_count': 0,
            'blocked': False, 'blocked_reasons': [],
            'labels': dict(LABELS[language]), 'scope': list(SCOPE), 'limitations': list(LIMITATIONS),
            'write': {'requested': False, 'status': 'not_requested', 'path': None, 'error': None}}


def _kind_for(message):
    for subject, kind in ADAPTER_PROBLEM_KINDS:
        if subject in message:
            return kind
    return 'schema'


def _registry(payload, root, base, path, clock, limit):
    """Reuse the existing agency adapter unchanged, then check what it does not claim."""
    entry = payload['registry']
    entry['present'] = path.is_file()
    if entry['present']:
        try:
            entry['sha256'] = pb.file_digest(path)
        except OSError as exc:
            _problem(payload, 'path', 'registry', 'Registry digest is unavailable: ' + str(exc), blocking=True)
    problems = []
    try:
        matched = pb.validate_agency_registry(path, base, root, problems)
    except (ValueError, OSError) as exc:
        _problem(payload, 'schema', 'registry',
                 'The existing agency registry could not be validated: ' + str(exc), blocking=True)
        return
    for message in problems:
        _problem(payload, _kind_for(message), 'registry', message)
    try:
        pb.agency_registry(path, base, root)
    except ValueError as exc:
        if not problems:
            _problem(payload, 'identity', 'registry', str(exc))
    except OSError as exc:
        _problem(payload, 'path', 'registry', 'The existing agency registry is unreadable: ' + str(exc),
                 blocking=True)
    entry['matched_entries'] = len(matched)
    entry['matched_ids'] = sorted({item['id'] for item in matched if isinstance(item.get('id'), str)})
    if not matched:
        _problem(payload, 'identity', 'registry.active_dir',
                 'No registered entry resolves to the selected canonical project root; the reporter '
                 'never falls back to another registered client')
        return
    if len(matched) > 1:
        _problem(payload, 'identity', 'registry.active_dir',
                 'Several registered entries resolve to the selected canonical project root: '
                 + ', '.join(entry['matched_ids']))
        return
    record = matched[0]
    identity = record.get('id')
    if identity != payload['project_id']:
        _problem(payload, 'identity', 'registry.id',
                 'The entry matching this root is registered as ' + repr(identity)
                 + ', not the explicitly requested ' + repr(payload['project_id']))
        return
    _entry(payload, record, base, clock, limit)


def _entry(payload, record, base, clock, limit):
    """Read the one registered entry the existing adapter already accepted for this root."""
    status = record.get('control_status')
    payload['control_status'] = status if isinstance(status, str) else None
    evidence_only = status in pb.AGENCY_EVIDENCE_ONLY
    payload['evidence_only'] = evidence_only
    action = record.get('next_action')
    payload['ownership'] = {'delivery_owner': record.get('delivery_owner'),
                            'next_action_owner': action.get('owner') if isinstance(action, dict) else None}
    operational = not evidence_only
    if evidence_only:
        _problem(payload, 'status', 'control_status',
                 'The ledger records this project as ' + str(status)
                 + '; that evidence-only state is reported, never reconciled or improved')
    verified = _recorded(record.get('last_verified_at'), clock, limit, 'last_verified_at', operational)
    payload['timestamps']['last_verified_at'] = verified
    if operational:
        _check_timestamp(payload, verified, 'last_verified_at')
    _snapshot(payload, record, base)
    _evidence(payload, record, base, clock, limit, operational)


def _snapshot(payload, record, base):
    """Report the recorded context snapshot without ever opening it as authority for anything."""
    snapshot = payload['context_snapshot']
    snapshot['recorded'] = record.get('context_snapshot')
    if snapshot['recorded'] is None:
        return
    resolved, refusal = _inside(base, snapshot['recorded'])
    if refusal:
        _problem(payload, 'path', 'context_snapshot', refusal)
        return
    snapshot['resolved'] = str(resolved)
    snapshot['present'] = resolved.is_file()
    if snapshot['present']:
        snapshot['size_bytes'] = resolved.stat().st_size


def _evidence(payload, record, base, clock, limit, operational):
    """Current evidence means the file on disk now, never a stored digest on its own."""
    current = payload['current_evidence']
    evidence = record.get('state_evidence')
    if not isinstance(evidence, dict):
        if operational:
            _problem(payload, 'missing', 'state_evidence',
                     'An operational status needs recorded state evidence')
        return
    current['recorded'] = evidence.get('path')
    current['recorded_sha256'] = evidence.get('sha256') if isinstance(evidence.get('sha256'), str) else None
    current['source_type'] = evidence.get('source_type')
    current['source_type_accepted'] = current['source_type'] in pb.AGENCY_EVIDENCE_SOURCES
    raw = evidence.get('path')
    if raw is not None:
        try:
            current['symlinked'] = (base / str(raw)).is_symlink()
        except (OSError, ValueError):
            current['symlinked'] = False
    resolved, refusal = _inside(base, raw) if raw is not None else (None, 'must name the evidence file')
    if refusal:
        _problem(payload, 'path', 'state_evidence.path', refusal)
        return
    current['resolved'] = str(resolved)
    current['present'] = resolved.exists()
    if not current['present']:
        _problem(payload, 'missing', 'state_evidence.path',
                 'The recorded state evidence file does not exist: ' + str(resolved))
        return
    if not resolved.is_file():
        _problem(payload, 'path', 'state_evidence.path', 'State evidence must be a regular file')
        return
    current['is_file'] = True
    if current['symlinked']:
        _problem(payload, 'path', 'state_evidence.path', 'State evidence may not be a symlink')
    current['hardlinks'] = resolved.stat().st_nlink
    if current['hardlinks'] != 1:
        _problem(payload, 'ownership', 'state_evidence.path',
                 'State evidence must not be a hardlink; it is linked to ' + str(current['hardlinks'])
                 + ' names and could be replaced through another of them')
    current['size_bytes'] = resolved.stat().st_size
    if not current['size_bytes']:
        _problem(payload, 'missing', 'state_evidence.path', 'State evidence is empty')
    try:
        current['current_sha256'] = pb.file_digest(resolved)
    except OSError as exc:
        _problem(payload, 'path', 'state_evidence.path', 'State evidence cannot be read: ' + str(exc))
        return
    current['digest_matches'] = (isinstance(evidence.get('sha256'), str)
                                 and current['current_sha256'] == evidence['sha256'].lower())
    if not current['digest_matches']:
        _problem(payload, 'hash', 'state_evidence.sha256',
                 'The recorded digest does not match the current evidence file on disk')
    observed = _recorded(evidence.get('observed_at'), clock, limit, 'state_evidence.observed_at', True)
    payload['timestamps']['state_evidence.observed_at'] = observed
    _check_timestamp(payload, observed, 'state_evidence.observed_at')


def _setup(payload, root, project_id):
    """Read the project's own enrollment state. Absent setup is reported, never created."""
    setup = payload['setup']
    try:
        config, relative = pb.load_config(root, pb.CONFIG_NAME)
        setup['config_path'] = relative
        setup['config_present'] = config is not None
    except ValueError as exc:
        _problem(payload, 'setup', pb.CONFIG_NAME, str(exc))
        config = None
    if config is not None:
        setup['config_project_id'] = config.get('project_id')
        if config.get('project_id') != project_id:
            _problem(payload, 'identity', pb.CONFIG_NAME,
                     'The portable project configuration declares project ID '
                     + repr(config.get('project_id')) + ', not the explicitly requested '
                     + repr(project_id))
    else:
        _problem(payload, 'setup', pb.CONFIG_NAME,
                 'Required setup: this project has no valid portable configuration; create it '
                 'explicitly with crewloom project enter, which this reporter never runs')
    try:
        binding = pb.load_binding(root, required=False)
        setup['binding_present'] = binding is not None
    except ValueError as exc:
        _problem(payload, 'setup', pb.BINDING_RELATIVE, str(exc))
        binding = None
    if binding is None:
        _problem(payload, 'setup', pb.BINDING_RELATIVE,
                 'Required setup: this project has no valid local Crewloom binding; create it '
                 'explicitly with crewloom project enter, which this reporter never runs')
    else:
        setup['binding_project_id'] = binding.get('project_id')
        if binding.get('project_id') != project_id:
            _problem(payload, 'identity', pb.BINDING_RELATIVE,
                     'The local binding declares project ID ' + repr(binding.get('project_id'))
                     + ', not the explicitly requested ' + repr(project_id))
    setup['enrolled'] = setup['config_present'] and setup['binding_present']


def _conclude(payload):
    """The verdict is derived only from recorded facts; the ledger's own status stays the headline."""
    payload['problem_count'] = len(payload['problems'])
    payload['missing_fields'] = sorted({item['field'] for item in payload['problems']
                                        if item['kind'] in ('missing', 'setup')})
    payload['blocked'] = any(item['blocking'] for item in payload['problems'])
    if payload['blocked']:
        outcome = 'blocked'
    elif payload['evidence_only']:
        outcome = 'needs_reconciliation'
    elif payload['problems']:
        outcome = 'not_ready'
    else:
        outcome = 'ready'
    payload['outcome'] = outcome
    payload['ready'] = outcome == 'ready'
    payload['exit_code'] = exit_code(payload)
    return payload


def report(project_id, project_root, agency_root, registry,
           max_evidence_age_seconds=DEFAULT_EVIDENCE_AGE_SECONDS, now=None, language='en'):
    """Assess one registered project and return the report; nothing on disk is written.

    Every input is explicit: the registered project ID, the canonical project root, the
    agency workspace root and the registry file. None of them is inferred from the working
    directory, a previous report, the registry location or a matching filename. `now`
    injects a timezone-aware instant so an age check can be exercised deterministically.
    """
    if not isinstance(project_id, str) or not pb.PROJECT_ID.fullmatch(project_id):
        raise ValueError('Explicit registered project ID is required: ' + repr(project_id))
    limit = _limit(max_evidence_age_seconds)
    clock = _clock(now)
    if language not in LANGUAGES:
        raise ValueError('Report language must be en or ar')
    payload = _payload(project_id, limit, clock, language)
    try:
        root = pb.project_root(project_root)
        base, path = _agency_paths(agency_root, registry)
    except (ValueError, OSError) as exc:
        _problem(payload, 'path', 'selected_paths', str(exc), blocking=True)
        return _conclude(payload)
    payload['project_root'] = str(root)
    payload['agency_root'] = str(base)
    payload['registry_path'] = str(path)
    _registry(payload, root, base, path, clock, limit)
    _setup(payload, root, project_id)
    return _conclude(payload)


def exit_code(payload):
    """Ready is zero. Anything else, including a refused report write, is exit two."""
    if payload.get('ready') and payload.get('write', {}).get('status') in ('not_requested', 'written'):
        return EXIT_READY
    return EXIT_NOT_READY


def _report_destination(root, relative):
    """One explicit report file, inside the reporter's own namespace of the project runtime.

    The order of the refusals is the order of the questions: the path must resolve inside the
    selected project first, then name project runtime state, then the reporter's own namespace,
    and only then be judged as a destination. Every refusal happens before a single byte is staged.
    """
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError('Explicit report path is required')
    value = relative.strip()
    if Path(value).is_absolute():
        raise ValueError('A readiness report path is selected-project relative: ' + value)
    path = w.safe_path(root, value, internal=True)
    parts = Path(value).parts
    if any(w.folded(part) == '.git' for part in parts):
        raise ValueError('A readiness report may not be written into Git state')
    owned = [w.folded(RUNTIME_DIRECTORY), w.folded(REPORT_NAMESPACE)]
    if [w.folded(part) for part in parts[:2]] != owned:
        raise ValueError('A readiness report may only be written inside the selected project '
                         + RUNTIME_DIRECTORY + '/' + REPORT_NAMESPACE + ' directory; runtime '
                         'authority and controller state are never written by this reporter')
    namespace = (root / RUNTIME_DIRECTORY / REPORT_NAMESPACE).resolve()
    if path == namespace or not path.is_relative_to(namespace):
        raise ValueError('A readiness report must stay inside ' + str(namespace))
    trusted = list(resources.installed_roots()) + [w.LIBRARY]
    if w.inside(path, trusted):
        raise ValueError('A readiness report may not be written inside the shared Crewloom runtime '
                         'or installed role and documentation resources')
    if path.exists() and not path.is_file():
        raise ValueError('The report destination must be a regular file')
    if path.exists() and path.stat().st_nlink != 1:
        raise ValueError('The report destination must not be a hardlink')
    if not path.parent.is_dir():
        raise ValueError('Create the owned readiness directory explicitly before writing a readiness '
                         'report; the reporter never creates ' + str(path.parent))
    return path


def _store(path, payload):
    """Bounded owner-only content, staged beside its destination and replaced in one step."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if len(text.encode('utf-8')) > MAX_REPORT_BYTES:
        raise ValueError('Readiness report exceeds the bounded size of ' + str(MAX_REPORT_BYTES) + ' bytes')
    descriptor, staged = tempfile.mkstemp(dir=str(path.parent), prefix='.agency-readiness-')
    stream = os.fdopen(descriptor, 'w', encoding='utf-8')
    try:
        os.fchmod(stream.fileno(), 0o600)
        with stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, str(path))
        staged = None
    finally:
        if staged is not None:
            try:
                os.unlink(staged)
            except OSError:
                pass


def _authorized_destination(payload, project_root, relative):
    """The one destination this exact report may be stored at, after its own identity registers cleanly."""
    if not isinstance(payload, dict) or payload.get('tool') != TOOL or payload.get('mode') != MODE:
        raise ValueError('Only a report produced by this reporter can be stored')
    root = pb.project_root(payload.get('project_root'))
    if project_root is not None and pb.project_root(project_root) != root:
        raise ValueError('The report and the explicit project root must be the same canonical project')
    try:
        registered = pb.agency_registry(Path(payload['registry_path']), Path(payload['agency_root']), root)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ValueError('The report is not stored for an unregistered project: ' + str(exc))
    if registered.get('project_id') != payload.get('project_id'):
        raise ValueError('The report is not stored for a different project identity')
    return _report_destination(root, relative)


def store_report(payload, project_root, relative):
    """Write one operator-selected report file, only after the same identity registers cleanly."""
    destination = _authorized_destination(payload, project_root, relative)
    _store(destination, payload)
    return destination


def _deliver(payload, relative):
    """A refused or failed report write is reported and never downgraded to a silent success."""
    entry = {'requested': True, 'status': 'refused', 'path': None, 'error': None}
    payload['write'] = entry
    try:
        destination = _authorized_destination(payload, payload.get('project_root'), relative)
        entry['path'] = str(destination)
        entry['status'] = 'written'
        _store(destination, payload)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        entry['status'] = 'refused'
        entry['path'] = None
        entry['error'] = str(exc)
        print(TOOL + ': ' + str(exc), file=sys.stderr)


def main(argv=None):
    """Report readiness for exactly one explicitly selected registered project."""
    parser = argparse.ArgumentParser(description='Read-only rollout readiness for one registered '
                                                 'agency project; prints JSON on stdout')
    parser.add_argument('--project-id', required=True,
                        help='Exact registered project ID recorded in the ledger')
    parser.add_argument('--project-root', required=True,
                        help='Existing canonical project root of that registration')
    parser.add_argument('--agency-root', required=True,
                        help='Explicit agency workspace root that holds the ledger')
    parser.add_argument('--registry', required=True,
                        help='Explicit agency project-control registry file')
    parser.add_argument('--max-evidence-age-seconds', type=int, default=DEFAULT_EVIDENCE_AGE_SECONDS,
                        help='Explicit evidence age limit in seconds (' + str(DEFAULT_EVIDENCE_AGE_SECONDS)
                             + ' by default)')
    parser.add_argument('--report-out',
                        help='Optional report file inside the selected project '
                             + SUGGESTED_REPORT_PATH + '; default is stdout only')
    parser.add_argument('--language', choices=LANGUAGES, default='en',
                        help='Human labels in the report; machine keys never change')
    args = parser.parse_args(argv)
    try:
        payload = report(args.project_id, args.project_root, args.agency_root, args.registry,
                         max_evidence_age_seconds=args.max_evidence_age_seconds, language=args.language)
    except (ValueError, OSError) as exc:
        print(json.dumps({'schema_version': REPORT_SCHEMA_VERSION, 'tool': TOOL, 'mode': MODE,
                          'outcome': 'error', 'ready': False, 'exit_code': EXIT_NOT_READY,
                          'error': str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
        print(TOOL + ': ' + str(exc), file=sys.stderr)
        return EXIT_NOT_READY
    if args.report_out:
        _deliver(payload, args.report_out)
        payload['exit_code'] = exit_code(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return payload['exit_code']


if __name__ == '__main__':
    sys.exit(main())