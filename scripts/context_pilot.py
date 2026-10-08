"""Reproducible cold/warm pilot for project context; provider usage stays explicitly unknown.

The pilot measures only what this repository can measure locally: index cold and warm
behaviour, selected versus full context bytes, recorded omissions and acceptance checks.
It never calls a provider, so token, cache and cost effects stay unknown. Two synthetic
project sizes are measured because bounded selection trades a small fixed overhead for a
large saving: the honest crossover is reported rather than assumed.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import project_binding as pb
import project_context as pc
import repo_map
import workflow as w

ROLE = 'context-guardian'
SEED = 'src/login.py'
SIZES = (('small', 20, 400), ('large', 600, 2400))
ACCEPTANCE_ARGV = ['python3', '-m', 'unittest', 'discover', '-s', 'tests']
# Every file the frozen acceptance check genuinely reads: the package it discovers, the
# modules those tests import, and the tests themselves. Declaring less breaks discovery.
SYNTHETIC_INPUTS = ('src/__init__.py', 'src/login.py', 'src/session.py',
                    'tests/__init__.py', 'tests/test_login.py', 'tests/test_acceptance.py')
ACCEPTANCE_OUTPUT = 'acceptance-report.txt'
# The only parts of a frozen generation a repeat measurement cannot reproduce byte for byte:
# the checkout's own identity, the identity-derived range cache keys and digests taken over
# them, the recorded scan timing, and the recorded total size those values change. Every other
# value is named by exact path, so measured counts, rule and body text, criteria, navigation,
# range lines and omissions stay exactly as recorded and are compared byte for byte.
VOLATILE_PAYLOAD_PATHS = (('bytes',), ('sha256',), ('semantic_sha256',), ('created_at',),
                          ('telemetry', 'generated_at'), ('telemetry', 'duration_ms'),
                          ('scope', 'project_root'), ('scope', 'checkout_id'),
                          ('map', 'checkout_id'))
VOLATILE_RANGE_KEYS = ('cache_key',)
NORMALIZED = '<normalized>'


def _blanked(value, path):
    if not path:
        return NORMALIZED
    if isinstance(value, dict) and path[0] in value:
        updated = dict(value)
        updated[path[0]] = _blanked(value[path[0]], path[1:])
        return updated
    return value


def normalized_payload(context, paths=VOLATILE_PAYLOAD_PATHS, range_keys=VOLATILE_RANGE_KEYS):
    """Return a copy with only the named identity and timing values replaced by one token."""
    normalized = dict(context)
    for path in paths:
        normalized = _blanked(normalized, path)
    if isinstance(normalized.get('ranges'), list):
        normalized['ranges'] = [dict(item, **{key: NORMALIZED for key in range_keys if key in item})
                               for item in normalized['ranges']]
    return normalized


def stable_payload(context):
    """Measure a generation without its volatile timing and identity values.

    Reports the digest of the exact normalized serialized payload, its semantic digest and
    the exact bytes those volatile values occupied, so a size difference between two
    measurements can be accounted for instead of tolerated.
    """
    actual = (pc.canonical(context) + '\n').encode()
    normalized = normalized_payload(context)
    stable = (pc.canonical(normalized) + '\n').encode()
    return {'stable_sha256': w.digest(stable), 'stable_semantic_sha256': pc.semantic_digest(normalized),
            'volatile_bytes': len(actual) - len(stable)}


def synthetic_project(root, modules=600, module_bytes=2400):
    """A deterministic fixture: one package, its tests, and unrelated modules."""
    # The pilot's own repository is disposable; it must never inherit the repository, index or
    # configuration of whatever checkout is running the pilot.
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True, env=repo_map.git_environment())
    import crewloom
    crewloom.install_skills(root, 'agents', [ROLE], False)
    (root / 'src').mkdir()
    (root / 'src' / '__init__.py').write_text('"""Pilot package."""\n', encoding='utf-8')
    (root / SEED).write_text(
        'from .session import Session\n\n\ndef login(user):\n    """Authenticate a user."""\n    return Session(user)\n',
        encoding='utf-8')
    (root / 'src' / 'session.py').write_text(
        'class Session:\n    def __init__(self, user):\n        self.user = user\n', encoding='utf-8')
    (root / 'tests').mkdir()
    (root / 'tests' / '__init__.py').write_text('"""Pilot acceptance tests."""\n', encoding='utf-8')
    # unittest collects TestCase classes on every supported interpreter; module-level
    # functions stopped being collected in Python 3.13.
    (root / 'tests' / 'test_login.py').write_text(
        'import unittest\n\nfrom src.login import login\n\n\n'
        'class LoginTest(unittest.TestCase):\n'
        '    def test_login(self):\n'
        '        self.assertEqual(login("a").user, "a")\n', encoding='utf-8')
    (root / 'tests' / 'test_acceptance.py').write_text(
        'import unittest\nfrom pathlib import Path\n\nfrom src.login import login\n\n\n'
        'class AcceptanceTest(unittest.TestCase):\n'
        '    def test_login_returns_session(self):\n'
        '        self.assertEqual(login("pilot").user, "pilot")\n\n'
        '    def test_acceptance_report_written(self):\n'
        '        Path("' + ACCEPTANCE_OUTPUT + '").write_text("acceptance executed\\n", encoding="utf-8")\n',
        encoding='utf-8')
    filler = 'def helper():\n    return "' + 'x' * (module_bytes - 40) + '"\n'
    for index in range(modules):
        (root / 'src' / ('module%04d.py' % index)).write_text(filler.replace('helper', 'helper_%04d' % index),
                                                              encoding='utf-8')
    (root / 'ACCEPTANCE.md').write_text('- login returns a session\n', encoding='utf-8')
    return root


def docker_available(image=None):
    """True only when the isolated executor can really start; never assumed from a binary name."""
    if not shutil.which('docker'):
        return False
    try:
        subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], capture_output=True,
                       text=True, timeout=30, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def acceptance_workflow(root, task_id, image, inputs):
    """Run the fixed acceptance command through the trusted Docker executor, then verify it.

    The plan declares every file the check reads and the single artifact it writes. Nothing
    is claimed here: without a declared input set the pilot reports executed=false.
    """
    missing = [name for name in inputs if not (root / name).is_file()]
    if missing:
        return {'executed': False, 'reason': 'declared acceptance inputs are missing: ' + ', '.join(missing),
                'command': ACCEPTANCE_ARGV, 'inputs': list(inputs), 'outputs': [ACCEPTANCE_OUTPUT]}
    plan = {'schema_version': 1, 'id': task_id, 'steps': [
        {'id': 'acceptance', 'role': ROLE, 'summary': 'Run the fixed acceptance check',
         'argv': list(ACCEPTANCE_ARGV), 'timeout_seconds': 120,
         'inputs': sorted(inputs), 'outputs': [ACCEPTANCE_OUTPUT]}]}
    if not w.ID.fullmatch(task_id):
        raise ValueError('Pilot task ID must be stable kebab-case')
    plan_file = '.crewloom/pilots/' + task_id + '/workflow.json'
    import continuation
    continuation._private_write(w.plan_source(root, plan_file), json.dumps(plan))
    parsed, fingerprint = w.read_plan(root, plan_file)
    try:
        result = w.run(root, parsed, fingerprint, image, plan_file=plan_file)
    except ValueError as exc:
        return {'executed': False, 'reason': str(exc), 'command': plan['steps'][0]['argv'],
                'inputs': plan['steps'][0]['inputs'], 'outputs': plan['steps'][0]['outputs']}
    executed = result.get('project_context') or {}
    return {'executed': True, 'status': result.get('status'),
            'managed_lifecycle': bool(result.get('project_context')),
            'verified': bool(executed.get('verified')),
            'context_status': executed.get('status'),
            'verification_runs': len(executed.get('verification') or []),
            'command': plan['steps'][0]['argv'],
            'inputs': plan['steps'][0]['inputs'], 'outputs': plan['steps'][0]['outputs'],
            'image': image,
            'note': 'acceptance ran inside the isolated Docker executor over the declared input set; '
                    'the task is verified only when recorded executor evidence is resolved'}


def measure(root, task_id='context-pilot', label='fixture', image=None, dry_run=False,
            project_id='pilot-project', role=ROLE, seed=SEED, declared=None, criteria_path='ACCEPTANCE.md',
            language=None, acceptance_inputs=None):
    """Measure one project. A real project is never initialized or altered to fit the pilot."""
    acceptance = {'executed': False, 'reason': 'dry run: no acceptance command was executed'}
    finalization = {'status': 'not-finalized', 'verified': False}
    if dry_run:
        binding = pb.load_binding(root)
        config, _ = pb.load_config(root)
    else:
        if pb.load_binding(root, required=False) is None:
            pb.bootstrap(root, project_id)
        acceptance = acceptance_workflow(root, task_id, image or w.DEFAULT_IMAGE,
                                        list(acceptance_inputs or SYNTHETIC_INPUTS))
        binding = pb.enter(root, project_id, task_id, role, seeds=[seed],
                           sources=list(declared) if declared else [seed], criteria_path=criteria_path,
                           language=language)
        config, _ = pb.load_config(root)
    cache = root / '.crewloom' / 'index' / 'map.json'
    if cache.exists():
        cache.unlink()
    cold_started = time.monotonic()
    _, cold = repo_map.build(root, config=config)
    cold['wall_ms'] = round((time.monotonic() - cold_started) * 1000)
    warm_started = time.monotonic()
    value, warm = repo_map.build(root, config=config)
    warm['wall_ms'] = round((time.monotonic() - warm_started) * 1000)
    navigation, selection = repo_map.render(value, 'login session', config['budgets']['map_bytes'], [seed])
    if dry_run:
        context = pc.snapshot(root, binding, task_id, role, config, [], [seed], language,
                              list(declared) if declared else [seed], criteria_path=criteria_path)
    else:
        context = pc.load(root, {'task_id': task_id, 'project_id': binding['project_id'],
                                 'checkout_id': binding['checkout_id'], 'project_root': str(root)})
    rules = sum(item['bytes'] for item in context['rules'])
    body_bytes = sum(item['bytes'] for item in context['bodies'])
    source_bytes = sum(len(w.safe_path(root, name).read_bytes()) for name in value['files'])
    criteria_bytes = sum(len(line.encode()) for line in context['criteria'])
    full_context_bytes = rules + criteria_bytes + source_bytes
    serialized = pc.payload_bytes(context)
    stable = stable_payload(context)
    if not dry_run:
        accepted = pb.finish(root, project_id, task_id, [seed], [],
                             evidence=[{'workflow': task_id, 'step': 'acceptance',
                                        'scope': 'pilot acceptance command'}])
        finalization = {'status': accepted['status'], 'verified': accepted['verified'],
                        'verification_runs': len(accepted['verification']),
                        'rejected_evidence': accepted['rejected_evidence']}
    return {
        'label': label, 'project_root': str(root), 'task_id': task_id, 'dry_run': bool(dry_run),
        'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
        'seed': seed, 'role': role, 'criteria_path': criteria_path, 'language': context['scope']['language'],
        'index': {'cold': cold, 'warm': warm, 'files': warm['files'], 'generation': warm['generation'],
                  'graph_complete': warm['graph_complete']},
        'context': {'selected_bytes': context['bytes'], 'serialized_bytes': serialized,
                    'rules_bytes': rules,
                    'declared_source_bytes': body_bytes, 'map_bytes': selection['map_bytes'],
                    'included_files': selection['included_files'], 'omitted_files': selection['omitted_files'],
                    'indexed_source_bytes': source_bytes, 'full_context_bytes': full_context_bytes,
                    'selected_share_of_full_context': round(context['bytes'] / max(1, full_context_bytes), 4),
                    'selection_wins': context['bytes'] < full_context_bytes,
'omissions': context['omissions'], 'generation': context['generation'],
                     'semantic_sha256': context['semantic_sha256'],
                     'stable_sha256': stable['stable_sha256'],
                     'stable_semantic_sha256': stable['stable_semantic_sha256'],
                     'volatile_bytes': stable['volatile_bytes']},
        'seed_visible': seed in navigation,
        'acceptance_command': acceptance,
        'finalization': finalization,
        'provider': {'usage_available': False, 'cached_tokens_available': False, 'cost_known': False,
                     'note': 'no provider call is made by this pilot; token, cache and cost effects stay unknown'},
        'acceptance': {
            'cold_parsed_every_file': cold['parsed'] == cold['files'],
            'warm_reused_every_file': warm['parsed'] == 0 and warm['reused'] == warm['files'],
            'seed_path_present': seed in navigation,
            'rules_included_completely': any(item['path'].endswith(role + '/SKILL.md')
                                             for item in context['rules']),
            'exact_serialized_bytes': serialized == context['bytes'],
            'acceptance_executed': bool(acceptance['executed']),
            'finalization_verified': bool(finalization['verified']),
            'stale_reference_refused': _stale_reference_refused(root, context, seed),
        },
    }


def _stale_reference_refused(root, context, seed):
    entry = next((item for item in context['ranges'] if item['path'] == seed), None)
    if entry is None:
        return False
    pc.resolve_range(root, context, entry['cache_key'], entry['path'], entry['start'], entry['end'])
    try:
        pc.resolve_range(root, context, 'f' * 64, entry['path'], entry['start'], entry['end'])
    except ValueError:
        return True
    return False


def run_suite(project=None, **options):
    """Measure the selected project, or both synthetic sizes for a reproducible comparison."""
    if project:
        return [measure(project, **options)]
    reports = []
    for label, modules, module_bytes in SIZES:
        with tempfile.TemporaryDirectory(prefix='crewloom-pilot-' + label + '-') as folder:
            reports.append(measure(synthetic_project(Path(folder).resolve(), modules, module_bytes),
                                   label=label, **options))
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', help='Existing bound project root; synthetic sizes are measured when omitted')
    parser.add_argument('--project-id', help='Portable project ID; defaults to the synthetic pilot fixture')
    parser.add_argument('--task-id', default='context-pilot')
    parser.add_argument('--role', default=ROLE)
    parser.add_argument('--seed', help='Project-relative seed path; defaults to the synthetic fixture seed')
    parser.add_argument('--source', action='append', default=[])
    parser.add_argument('--criteria', help='Project-relative acceptance criteria file')
    parser.add_argument('--language', choices=('en', 'ar'))
    parser.add_argument('--image', default=w.DEFAULT_IMAGE)
    parser.add_argument('--acceptance-input', action='append', default=[],
                        help='Project-relative file the acceptance check reads; repeat for each real dependency')
    parser.add_argument('--dry-run', action='store_true',
                        help='Measure without entering the project, running acceptance or finalizing')
    parser.add_argument('--out', help='Write the pilot report to this path instead of stdout')
    args = parser.parse_args(argv)
    try:
        root = pb.project_root(args.project) if args.project else None
        if root is not None:
            binding = pb.load_binding(root, required=False)
            if binding is None:
                raise ValueError('A real project must already be bound; the pilot never initializes one')
            if not args.seed:
                raise ValueError('A real project needs an explicit --seed; the fixture seed is never assumed')
            if not args.criteria:
                raise ValueError('A real project needs an explicit --criteria file')
            project_id = args.project_id or binding['project_id']
        else:
            project_id = args.project_id or 'pilot-project'
        options = {'image': args.image, 'dry_run': args.dry_run,
                   'project_id': project_id,
                   'role': args.role, 'seed': args.seed or SEED,
                   'declared': args.source,
                   'criteria_path': args.criteria or 'ACCEPTANCE.md', 'language': args.language,
                   'acceptance_inputs': args.acceptance_input or None}
        options['task_id'] = args.task_id
        reports = run_suite(root, **options)
        suite = {'measurements': reports,
                 'crossover': {report['label']: report['context']['selected_share_of_full_context']
                               for report in reports},
                 'note': 'bounded selection pays for itself once the indexed source exceeds its fixed overhead',
                 'acceptance_note': 'acceptance runs only inside the isolated Docker executor over the '
                                    'declared input set; nothing else is ever claimed as verification',
                 'provider': reports[0]['provider']}
        payload = json.dumps(suite, ensure_ascii=False, indent=2)
        if args.out:
            target = Path(args.out).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload + '\n', encoding='utf-8')
            print('pilot: ' + str(target))
        else:
            print(payload)
        failures = sorted({name for report in reports for name, ok in report['acceptance'].items()
                           if not ok and not (args.dry_run and name in ('acceptance_executed',
                                                                        'finalization_verified'))})
        if reports[-1]['label'] == 'large' and not reports[-1]['context']['selection_wins']:
            failures.append('large_project_selection_wins')
        return 0 if not failures else 2
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
