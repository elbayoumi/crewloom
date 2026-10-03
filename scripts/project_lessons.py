"""Evidence-linked project lessons with explicit candidate and verified states.

A lesson is promoted only from evidence this checkout's own executor recorded in
workflow state: real exit codes, real artifact fingerprints and the project scope
they were produced under. Model prose, operator-supplied JSON and native or
externally attested claims stay candidates until independently verified. Failed
attempts remain labelled negative evidence, deduplication preserves provenance,
changed policy invalidates a lesson, and stored commands are never executed here.
"""
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import workflow as w

SCHEMA_VERSION = 1
STATES = ('candidate', 'verified', 'invalidated', 'superseded')
CONDITIONS = ('paths', 'languages', 'symbols', 'policy_sha256', 'dependencies')
MAX_LESSONS = 500
MAX_EXPORT = 100
IDENTIFIER = re.compile(r'[0-9a-f]{32}$')
KKEBAB = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*$')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def folder(root):
    path = w.safe_path(root, '.crewloom/lessons', internal=True)
    if path.is_symlink():
        raise ValueError('Lesson storage may not be a symlink')
    path.mkdir(parents=True, exist_ok=True)
    return path


def dedupe_key(issue, conditions):
    return w.digest(canonical({'issue': issue.strip().casefold(),
                               'conditions': {key: sorted(value) if isinstance(value, list) else value
                                              for key, value in sorted(conditions.items())}}).encode())


def read(root, lesson_id):
    if not isinstance(lesson_id, str) or not IDENTIFIER.fullmatch(lesson_id):
        raise ValueError('Lesson ID must be a 32-character identifier')
    path = w.safe_path(root, '.crewloom/lessons/' + lesson_id + '.json', internal=True)
    if not path.is_file():
        raise ValueError('Unknown lesson: ' + lesson_id)
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA_VERSION or value.get('id') != lesson_id:
        raise ValueError('Malformed lesson record: ' + lesson_id)
    if value.get('state') not in STATES:
        raise ValueError('Malformed lesson state: ' + lesson_id)
    if value['scope'].get('project_root') != str(Path(root).resolve()):
        raise ValueError('Lesson belongs to another project root')
    return value


def save(root, value):
    path = w.safe_path(root, '.crewloom/lessons/' + value['id'] + '.json', internal=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(canonical(value) + '\n', encoding='utf-8')
    temporary.replace(path)
    return value


def all_lessons(root):
    found = []
    for path in sorted(folder(root).glob('*.json')):
        if not IDENTIFIER.fullmatch(path.stem):
            continue
        found.append(read(root, path.stem))
    return found[:MAX_LESSONS]


def validate_conditions(conditions):
    if conditions is None:
        return {}
    if not isinstance(conditions, dict) or set(conditions) - set(CONDITIONS):
        raise ValueError('Lesson conditions must be a subset of: ' + ', '.join(CONDITIONS))
    for key, value in conditions.items():
        if key == 'policy_sha256':
            if value is not None and not re.fullmatch(r'[0-9a-f]{64}', str(value)):
                raise ValueError('policy_sha256 condition must be a SHA-256 fingerprint')
        elif not isinstance(value, list) or len(value) > 64 or any(not isinstance(item, str) or not item for item in value):
            raise ValueError('Lesson condition lists must hold at most 64 nonempty strings')
    return conditions


def policy_fingerprint(root, binding):
    config = Path(root) / 'crewloom.project.json'
    return {'policy_sha256': w.digest(config.read_bytes()) if config.is_file() else None,
            'project_id': binding['project_id'], 'checkout_id': binding['checkout_id']}


def source_fingerprints(root, paths):
    """Hash the declared sources a lesson was observed against, for later revalidation."""
    found = {}
    for relative in sorted({str(item) for item in (paths or [])}):
        path = w.safe_path(root, relative)
        found[relative] = w.digest(path.read_bytes()) if path.is_file() else None
    return found


def record(root, binding, issue, remedy, conditions=None, source_task=None, role=None,
           negative=False, verification=None, declared=None):
    """Create a candidate lesson, or extend the existing record with the same issue and conditions."""
    if not isinstance(binding, dict) or binding.get('project_root') != str(Path(root).resolve()):
        raise ValueError('Lesson binding belongs to another project root')
    for field, value in (('issue', issue), ('remedy', remedy)):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError('Lesson ' + field + ' must be nonempty text within 2000 characters')
    conditions = validate_conditions(conditions)
    key = dedupe_key(issue, conditions)
    existing = [item for item in all_lessons(root) if item['dedupe_key'] == key]
    if existing:
        value = existing[0]
        value.setdefault('provenance', {}).setdefault('observations', []).append(
            {'at': now(), 'task': source_task, 'role': role, 'negative': bool(negative)})
        if negative and not value.get('negative'):
            value['negative'] = True
        if isinstance(verification, dict):
            value.setdefault('attempts', []).append({'at': now(), **verification})
        value['provenance']['updated_at'] = now()
        save(root, value)
        return {'lesson': value, 'deduplicated': True}
    lesson_id = uuid.uuid4().hex
    value = {'schema_version': SCHEMA_VERSION, 'id': lesson_id, 'state': 'candidate', 'dedupe_key': key,
             'issue': issue.strip(), 'remedy': remedy.strip(), 'conditions': conditions,
             'negative': bool(negative), 'source_task': source_task, 'role': role,
             'declared_sources': sorted({str(item) for item in (declared or [])})[:32],
             'verification': verification if isinstance(verification, dict) else
                            {'kind': 'none', 'executed': False,
                             'note': 'no objective check has been executed for this lesson'},
             'command_execution': 'never-automatic; lesson commands are references for a human operator',
             'scope': {'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
                       'project_root': str(Path(root).resolve()), 'task_id': source_task},
             'fingerprints': policy_fingerprint(root, binding),
             'source_fingerprints': source_fingerprints(root, declared),
             'provenance': {'created_at': now(), 'updated_at': now(),
                            'observations': [{'at': now(), 'task': source_task, 'role': role, 'negative': bool(negative)}]},
             'attempts': [], 'supersedes': None, 'exported': False}
    save(root, value)
    return {'lesson': value, 'deduplicated': False}


def executor_evidence(root, references, binding=None, purpose='verification'):
    """Resolve real executor records from this project's workflow state and attempt ledger.

    Assumed trusted executor: the managed runner writes workflow state and the attempt
    ledger inside the project lock, so an attacker with unrestricted host write access
    can still forge both files. This closes API and state-evidence shortcuts (missing
    ledger, missing signature, uncorrelated identifiers, cross-scope reuse, stale
    artifacts), not an arbitrary host rewrite of every project file.
    """
    resolved = []
    if not isinstance(references, list) or not references:
        raise ValueError(purpose + ' needs at least one executor evidence reference')
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError('Each evidence reference must name a workflow and a step')
        workflow_id, step_id = reference.get('workflow'), reference.get('step')
        for value, label in ((workflow_id, 'workflow'), (step_id, 'step')):
            if not isinstance(value, str) or not KKEBAB.fullmatch(value):
                raise ValueError('Evidence reference needs an explicit lowercase ' + label + ' identifier')
        unknown = set(reference) - {'workflow', 'step', 'scope'}
        if unknown:
            raise ValueError('Evidence reference has unverified claims: ' + ', '.join(sorted(unknown)))
        state_file = w.safe_path(root, '.crewloom/workflows/' + workflow_id + '/state.json', internal=True)
        if not state_file.is_file():
            raise ValueError('No executor evidence recorded for workflow: ' + workflow_id)
        state = json.loads(state_file.read_text())
        if state.get('project_root') != str(Path(root).resolve()) or state.get('workflow') != workflow_id:
            raise ValueError('Workflow evidence belongs to another project or workflow: ' + workflow_id)
        if binding is not None:
            if state.get('project_id') != binding.get('project_id') or state.get('checkout_id') != binding.get('checkout_id'):
                raise ValueError('Workflow evidence belongs to another project or checkout: ' + workflow_id)
        record_state = (state.get('steps') or {}).get(step_id)
        if not isinstance(record_state, dict) or record_state.get('status') not in ('complete', 'failed'):
            raise ValueError('Evidence reference is not a recorded executor step: ' + step_id)
        if not isinstance(record_state.get('argv'), list) or not record_state['argv']:
            raise ValueError('Acceptance evidence needs a recorded command step: ' + step_id)
        if record_state.get('kind') not in (None, 'command'):
            raise ValueError('Acceptance evidence needs a command step, not a task or model step: ' + step_id)
        attempts = [attempt for attempt in record_state.get('attempts', [])
                    if attempt.get('status') == 'finished' and type(attempt.get('exit_code')) is int]
        if not attempts:
            raise ValueError('Evidence reference has no recorded executor attempt: ' + step_id)
        attempt = attempts[-1]
        signature = attempt.get('signature')
        if not isinstance(signature, str) or not re.fullmatch(r'[0-9a-f]{64}', signature):
            raise ValueError('Executor attempt has no recorded signature: ' + step_id)
        outputs = dict(record_state.get('outputs') or {})
        inputs = dict(record_state.get('inputs') or {})
        if record_state['status'] == 'complete' and not outputs:
            raise ValueError('Acceptance evidence needs validated output artifacts: ' + step_id)
        artifacts_ok = True
        observed = {}
        stale_outputs = []
        for relative, recorded in sorted(outputs.items()):
            if not re.fullmatch(r'[0-9a-f]{64}', str(recorded)):
                artifacts_ok = False
                stale_outputs.append(relative)
                continue
            path = w.safe_path(root, relative)
            if not path.is_file():
                artifacts_ok = False
                stale_outputs.append(relative)
                continue
            current = w.digest(path.read_bytes())
            observed[relative] = current
            if current != recorded:
                artifacts_ok = False
                stale_outputs.append(relative)
        consumed = {}
        for relative, recorded in sorted(inputs.items()):
            if relative in outputs:
                continue
            if not re.fullmatch(r'[0-9a-f]{64}', str(recorded)):
                consumed[relative] = 'input hash was never recorded'
                continue
            path = w.safe_path(root, relative)
            if not path.is_file():
                consumed[relative] = 'missing-since-execution'
            elif w.digest(path.read_bytes()) != recorded:
                consumed[relative] = 'changed-since-execution'
        failed_attempts = [{'exit_code': item['exit_code'], 'signature': item.get('signature')}
                           for item in attempts[:-1] if item['exit_code']]
        # The executor outcome is what the ledger recorded; artifact or input drift afterwards
        # is a separate, labelled failure rather than a rewritten execution history.
        executor_ok = attempt['exit_code'] == 0 and record_state['status'] == 'complete'
        passed = executor_ok and artifacts_ok and not consumed
        if attempt['exit_code']:
            reason = 'command failed'
        elif record_state['status'] != 'complete':
            reason = 'executor recorded no complete step for this reference'
        elif stale_outputs:
            reason = 'recorded outputs no longer match the artifacts: ' + ', '.join(stale_outputs[:8])
        elif consumed:
            reason = 'inputs changed or vanished after execution: ' + ', '.join(sorted(consumed)[:8])
        else:
            reason = None
        resolved.append({'workflow': workflow_id, 'step': step_id, 'command': list(record_state['argv']),
                         'exit_code': attempt['exit_code'], 'passed': passed,
                         'failure_reason': reason,
                         'source': 'project-executor-state', 'step_status': record_state['status'],
                         'executor_passed': executor_ok,
                         'scope': str(reference.get('scope') or ('step ' + step_id))[:300],
                         'inputs': inputs, 'outputs': outputs, 'observed_output_sha256': observed,
                         'consumed_inputs_changed': consumed,
                         'attempt_signature': signature, 'image_id': attempt.get('image_id'),
                         'prior_failures_retained': failed_attempts})
    ledger = w.safe_path(root, '.crewloom/attempts.json', internal=True)
    if not ledger.is_file():
        raise ValueError('Project attempt ledger is missing; executor evidence cannot be trusted')
    ledger_value = json.loads(ledger.read_text())
    entries = ledger_value.get('attempts') if isinstance(ledger_value, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError('Project attempt ledger is empty; executor evidence cannot be trusted')
    for item in resolved:
        matching = [entry for entry in entries if isinstance(entry, dict) and entry.get('signature') == item['attempt_signature']]
        if not matching:
            raise ValueError('Executor evidence is not present in the project attempt ledger: '
                             + item['workflow'] + '/' + item['step'])
        if any(entry.get('kind') == 'model' for entry in matching):
            raise ValueError('Provider generation is not an acceptance check: '
                             + item['workflow'] + '/' + item['step'])
        # The ledger must record the same executor outcome as the step state; a claim needs a
        # succeeded entry and a genuine failure stays correlated as a recorded failure.
        correlated = 'succeeded' if item['executor_passed'] else 'failed'
        if not any(entry.get('workflow') == item['workflow'] and entry.get('step') == item['step']
                   and entry.get('status') == correlated for entry in matching):
            raise ValueError('Attempt ledger entry does not correlate to this workflow step: '
                             + item['workflow'] + '/' + item['step'])
    return resolved


def verify(root, lesson_id, references, reviewer=None):
    """Promote only on executed objective checks recorded by this project's executor."""
    value = read(root, lesson_id)
    if value['state'] not in ('candidate', 'verified'):
        raise ValueError('Only a candidate lesson can be verified: ' + value['state'])
    resolved = executor_evidence(root, references, value['scope'], 'Promotion')
    current = policy_fingerprint(root, {'project_id': value['scope']['project_id'],
                                        'checkout_id': value['scope']['checkout_id']})
    if value['fingerprints'].get('policy_sha256') != current['policy_sha256']:
        return invalidate(root, lesson_id, 'policy configuration changed since the lesson was recorded')
    failures = [item for item in resolved if not item['passed']]
    value['verification'] = {'kind': 'objective', 'executed': True, 'evidence': resolved,
                             'reviewer': str(reviewer or 'unreviewed')[:100],
                             'proves': 'tested scope only; not universal correctness',
                             'at': now()}
    value['provenance']['updated_at'] = now()
    if failures:
        value['state'] = 'candidate'
        value['negative'] = True
        value.setdefault('negative_history', []).append(
            {'at': now(), 'failed': [item['step'] for item in failures],
             'failure_reasons': [item['failure_reason'] for item in failures]})
        value['attempts'].append({'at': now(), 'failed': [item['step'] for item in failures]})
        save(root, value)
        return value
    # A later objective pass makes the remedy retrievable again; the earlier failures stay
    # in negative_history, attempts and provenance instead of silently disappearing.
    if value.get('negative'):
        value.setdefault('negative_history', []).append(
            {'at': now(), 'superseded_by': 'a later objective verification passed',
             'earlier_failures': list(value.get('attempts', []))})
    value['negative'] = False
    value['state'] = 'verified'
    save(root, value)
    return value


def attach_external_attestation(root, lesson_id, attestation):
    """Native or external claims are recorded for review and never promote on their own."""
    value = read(root, lesson_id)
    if not isinstance(attestation, dict) or not attestation.get('source'):
        raise ValueError('An external attestation needs a named source and its claim')
    value['attestations'] = value.get('attestations', []) + [{**{k: str(v)[:300] for k, v in attestation.items()},
                                                              'at': now(), 'state_effect': 'none; review required'}]
    value['provenance']['updated_at'] = now()
    save(root, value)
    return value


def invalidate(root, lesson_id, reason):
    value = read(root, lesson_id)
    value['state'] = 'invalidated'
    value['provenance']['updated_at'] = now()
    value['provenance'].setdefault('invalidations', []).append({'at': now(), 'reason': str(reason)[:300]})
    save(root, value)
    return value


def supersede(root, lesson_id, replacement_id, reason):
    value = read(root, lesson_id)
    read(root, replacement_id)
    if value['state'] == 'superseded':
        return value
    value.update({'state': 'superseded', 'superseded_by': replacement_id,
                  'supersede_reason': str(reason)[:300]})
    value['provenance']['updated_at'] = now()
    save(root, value)
    return value


def revalidate(root, policy_sha256=None):
    """Changed policy, dependencies or recorded artifacts invalidate verified lessons."""
    changed = []
    for value in all_lessons(root):
        if value['state'] != 'verified':
            continue
        reason = None
        if policy_sha256 and value['fingerprints'].get('policy_sha256') != policy_sha256:
            reason = 'policy configuration changed'
        if reason is None:
            for relative, recorded in sorted((value.get('source_fingerprints') or {}).items()):
                path = w.safe_path(root, relative)
                current = w.digest(path.read_bytes()) if path.is_file() else None
                if current != recorded:
                    reason = 'declared source changed: ' + relative
                    break
        if reason is None:
            for item in value.get('verification', {}).get('evidence', []):
                for relative, recorded in sorted((item.get('observed_output_sha256') or {}).items()):
                    path = w.safe_path(root, relative)
                    if not path.is_file() or w.digest(path.read_bytes()) != recorded:
                        reason = 'verified artifact changed: ' + relative
                        break
                if reason:
                    break
        if reason is None:
            # Declared inputs are re-hashed too, so a verified remedy cannot be reused after
            # the sources its acceptance consumed changed underneath it.
            for item in value.get('verification', {}).get('evidence', []):
                for relative, recorded in sorted((item.get('inputs') or {}).items()):
                    if relative in (item.get('outputs') or {}):
                        continue
                    path = w.safe_path(root, relative)
                    current = w.digest(path.read_bytes()) if path.is_file() else None
                    if current != recorded:
                        reason = 'verified input changed: ' + relative
                        break
                if reason:
                    break
        if reason:
            invalidate(root, value['id'], reason)
            changed.append(value['id'])
    return changed


def matches(value, seeds, tokens):
    conditions = value.get('conditions') or {}
    if conditions.get('policy_sha256') and conditions['policy_sha256'] != value['fingerprints'].get('policy_sha256'):
        return False
    haystack = set(seed.casefold() for seed in seeds) | tokens
    for key in ('paths', 'languages', 'symbols'):
        wanted = conditions.get(key) or []
        if not wanted:
            continue
        joined = ' '.join(sorted(haystack))
        if not any(re.search(str(item).casefold(), joined) for item in wanted):
            return False
    return True


def select(root, seeds, tokens, limit):
    """Verified lessons that match these conditions, bounded, with negative evidence labelled."""
    if type(limit) is not int or limit < 0:
        raise ValueError('Lesson selection limit must be a non-negative integer')
    chosen = []
    negatives = 0
    omitted = 0
    for value in all_lessons(root):
        if not matches(value, seeds, tokens):
            continue
        if value['state'] == 'verified':
            if len(chosen) >= limit:
                omitted += 1
                continue
            chosen.append({'id': value['id'], 'state': value['state'], 'issue': value['issue'],
                           'remedy': value['remedy'], 'conditions': value['conditions'],
                           'verification': value['verification'], 'negative': False,
                           'source_task': value.get('source_task'), 'fingerprints': value['fingerprints'],
                           'command_execution': value['command_execution']})
        elif value.get('negative') and value['state'] in ('candidate', 'invalidated'):
            negatives += 1
    return {'lessons': chosen, 'negative_evidence_count': negatives, 'omitted': omitted,
            'policy': 'verified lessons only; failed attempts stay as labelled negative evidence'}


def record_from_task(root, binding, task_id, entries, checks, role=None):
    """Finalization records candidate lessons; promotion stays with executor evidence."""
    results = []
    for item in entries:
        if not isinstance(item, dict) or not item.get('issue') or not item.get('remedy'):
            raise ValueError('Each lesson entry needs an issue and a remedy')
        outcome = record(root, binding, item['issue'], item['remedy'], item.get('conditions'),
                         source_task=task_id, role=role, negative=bool(item.get('negative')),
                         verification={'kind': 'task-finalization',
                                       'executed_checks': len(checks),
                                       'failed_checks': [entry.get('command') or entry.get('workflow', '')
                                                         for entry in checks if not entry.get('passed')],
                                       'note': 'candidate only; promotion needs executor evidence'}
                         if checks else None,
                         declared=item.get('declared_sources'))
        lesson = outcome['lesson']
        results.append({'id': lesson['id'], 'state': lesson['state'], 'verified': False,
                        'deduplicated': outcome['deduplicated'], 'negative': bool(lesson.get('negative')),
                        'promotion_requires': 'executor evidence from a completed workflow step'})
    return results


def export_reviewed(root, destination, approved, reviewer):
    """Explicit, reviewed export only; project identity is verified and nothing is exported silently."""
    if not approved:
        raise ValueError('Export needs at least one reviewed lesson ID')
    lessons = []
    for lesson_id in approved:
        value = read(root, lesson_id)
        if value['state'] != 'verified':
            raise ValueError('Only verified lessons can be exported: ' + lesson_id)
        lessons.append({'id': value['id'], 'issue': value['issue'], 'remedy': value['remedy'],
                        'conditions': value['conditions'], 'verification': value['verification'],
                        'sanitized': True, 'source_project_id': value['scope']['project_id']})
        save(root, dict(value, exported=True))
    if len(lessons) > MAX_EXPORT:
        raise ValueError('Export packet exceeds its limit')
    packet = {'schema_version': SCHEMA_VERSION, 'project_id': read(root, approved[0])['scope']['project_id'],
              'reviewer': str(reviewer)[:100], 'exported_at': now(), 'lessons': lessons,
              'instruction': 'Reviewed project knowledge only; importing into another project re-verifies evidence.'}
    target = Path(destination).resolve()
    if target.is_relative_to(Path(root).resolve() / '.crewloom'):
        raise ValueError('Export packets belong outside runtime state; choose a reviewed destination')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical(packet) + '\n', encoding='utf-8')
    return str(target)


def import_reviewed(root, destination, binding):
    """Import verifies project identity, rejects cross-project packets and keeps evidence to re-verify."""
    source = Path(destination)
    if not source.is_file() or source.is_symlink():
        raise ValueError('Lesson packet not found: ' + str(destination))
    packet = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(packet, dict) or packet.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Malformed lesson packet')
    if packet.get('project_id') != binding['project_id']:
        raise ValueError('Lesson packet belongs to another project; review and re-record it locally')
    if binding.get('project_root') != str(Path(root).resolve()):
        raise ValueError('Lesson import binding belongs to another project root')
    imported = []
    for item in packet.get('lessons', [])[:MAX_EXPORT]:
        if not isinstance(item, dict) or not item.get('sanitized'):
            raise ValueError('Only sanitized reviewed lesson packets can be imported')
        lesson_id = uuid.uuid4().hex
        value = {'schema_version': SCHEMA_VERSION, 'id': lesson_id, 'state': 'candidate',
                 'dedupe_key': dedupe_key(str(item.get('issue', '')), validate_conditions(item.get('conditions'))),
                 'issue': str(item.get('issue', ''))[:2000], 'remedy': str(item.get('remedy', ''))[:2000],
                 'conditions': item.get('conditions') or {}, 'negative': False,
                 'source_task': None, 'role': None, 'declared_sources': [],
                 'verification': {'kind': 'imported-review-reference', 'executed': False,
                                  'note': 'imported evidence must be re-verified with this project executor'},
                 'command_execution': 'never-automatic; lesson commands are references for a human operator',
                 'scope': {'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
                           'project_root': str(Path(root).resolve()), 'task_id': None},
                 'fingerprints': policy_fingerprint(Path(root).resolve(), binding),
                 'source_fingerprints': {},
                 'provenance': {'created_at': now(), 'updated_at': now(),
                                'observations': [{'at': now(), 'task': None, 'role': None, 'negative': False}],
                                'imported_from': str(source)},
                 'attempts': [], 'supersedes': None, 'exported': False, 'imported': True}
        save(root, value)
        imported.append(lesson_id)
    return imported


def _binding(root):
    import project_binding
    return project_binding.load_binding(root)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('record', 'verify', 'attest', 'select', 'list', 'invalidate',
                                           'supersede', 'export', 'import', 'revalidate'))
    parser.add_argument('--project', required=True)
    parser.add_argument('--lesson-id', action='append', default=[])
    parser.add_argument('--issue'); parser.add_argument('--remedy')
    parser.add_argument('--conditions', default='{}')
    parser.add_argument('--task-id'); parser.add_argument('--role')
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--evidence', help='JSON list of {workflow, step, scope} executor evidence references')
    parser.add_argument('--attestation', help='JSON object naming an external source and its claim')
    parser.add_argument('--reviewer'); parser.add_argument('--reason')
    parser.add_argument('--by'); parser.add_argument('--out'); parser.add_argument('--packet')
    parser.add_argument('--seed', action='append', default=[])
    args = parser.parse_args(argv)
    if args.action in ('verify', 'attest', 'invalidate') and not args.lesson_id:
        parser.error('This action needs --lesson-id')
    if args.action == 'supersede' and not args.by:
        parser.error('Supersede needs --by with the replacement lesson ID')
    try:
        root = Path(args.project).resolve(strict=True)
        binding = _binding(root)
        if args.action == 'record':
            outcome = record(root, binding, args.issue, args.remedy, json.loads(args.conditions),
                             args.task_id, args.role, args.negative)
            result = {'lesson_id': outcome['lesson']['id'], 'state': outcome['lesson']['state'],
                      'deduplicated': outcome['deduplicated']}
        elif args.action == 'verify':
            value = verify(root, args.lesson_id[0], json.loads(args.evidence or '[]'), args.reviewer)
            result = {'lesson_id': value['id'], 'state': value['state'],
                      'evidence': value['verification'].get('evidence', [])}
        elif args.action == 'attest':
            result = {'lesson': attach_external_attestation(root, args.lesson_id[0],
                                                           json.loads(args.attestation or '{}'))}
        elif args.action == 'select':
            result = select(root, args.seed, set(), 24)
        elif args.action == 'list':
            result = {'lessons': [{'id': item['id'], 'state': item['state'], 'negative': item.get('negative'),
                                   'issue': item['issue'][:120]} for item in all_lessons(root)]}
        elif args.action == 'invalidate':
            result = {'lesson': invalidate(root, args.lesson_id[0], args.reason or 'operator review')}
        elif args.action == 'supersede':
            result = {'lesson': supersede(root, args.lesson_id[0], args.by, args.reason or 'superseded')}
        elif args.action == 'export':
            result = {'packet': export_reviewed(root, args.out, args.lesson_id, args.reviewer or 'unreviewed')}
        elif args.action == 'import':
            result = {'imported': import_reviewed(root, args.packet, binding),
                      'state': 'candidate; imported evidence must be re-verified locally'}
        else:
            result = {'invalidated': revalidate(root)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
