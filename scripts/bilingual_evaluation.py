"""Frozen bilingual feature pilot reusing the existing isolated held-out case grader.

This evaluates one developer role on two contracts, not all roles or provider superiority.
The generated candidate sees requirements only; expectations stay outside its container.
"""
import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import crewloom_resources as resources
import evaluate_hosts as grading
import model_host
import workflow as w

TASKS = 'examples/bilingual-evaluation/tasks.json'
ROLE = 'fullstack-mvp-engineer'


def frozen_inputs():
    root = resources.distribution_root()
    paths = [root / TASKS, root / '.agents/skills' / ROLE / 'SKILL.md',
             Path(__file__), Path(model_host.__file__), Path(grading.__file__), Path(w.__file__)]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(output, hosts, timeout=120, image=w.DEFAULT_IMAGE, seed=20261010, models=None):
    if not hosts or any(h not in model_host.CLI_HOSTS for h in hosts) or len(set(hosts)) != len(hosts):
        raise ValueError('Select distinct supported CLI hosts')
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError('Timeout must be from 1 to 600 seconds')
    models = models or {}
    if set(models) - set(hosts) or any(not isinstance(v, str) or not v.strip() for v in models.values()):
        raise ValueError('Explicit models must belong to selected hosts')
    folder = Path(output).absolute()
    if folder.exists() or folder.is_symlink():
        raise ValueError('Select a new output directory; attempts cannot be overwritten')
    folder.mkdir(parents=True, mode=0o700)
    root = resources.distribution_root()
    tasks = json.loads((root / TASKS).read_text())['tasks']
    image_id = w.inspect_image(image)
    frozen = frozen_inputs()
    trials = [{'host': host, 'task': task['id'], 'language': language}
              for host in hosts for task in tasks for language in ('en', 'ar')]
    random.Random(seed).shuffle(trials)
    report = {'protocol': 'crewloom-bilingual-feature-pilot-v1', 'seed': seed, 'image_id': image_id,
              'frozen_inputs': frozen, 'models_requested': models, 'planned_trials': trials, 'trials': [],
              'limits': 'One developer role, two synthetic contracts, one trial per language/host/task. No comparative quality or billing claim. CLI generation is an explicit native host exception.'}
    def save():
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    save()
    failures = {}; stopped = set()
    role = (root / '.agents/skills' / ROLE / 'SKILL.md').read_text()
    for index, trial in enumerate(trials):
        if frozen_inputs() != frozen:
            raise ValueError('Frozen evaluation inputs changed; report is invalid')
        result = {**trial, 'status': 'pending'}
        task = next(t for t in tasks if t['id'] == trial['task'])
        if trial['host'] in stopped:
            result.update(status='blocked', error='Host stopped after two identical transport failures')
        else:
            try:
                prompt = 'Follow this developer role. No tools or external files. Return the declared artifact only.\n' + role + '\nTask:\n' + task['prompts'][trial['language']]
                artifacts, evidence = model_host.generate(trial['host'], prompt, [task['output']], timeout, models.get(trial['host']))
                source = artifacts[task['output']].encode()
                (folder / ('candidate-%02d.py' % index)).write_bytes(source)
                cases = [grading._grade_case(source, task, case, 0, image_id, 15, root, (),
                                            Path(task['output']).name) for case in task['cases']]
                result.update(status='scored', evidence=evidence, source_sha256=w.digest(source),
                              passed=sum(c['passed'] for c in cases), total=len(cases), cases=cases)
            except (ValueError, OSError) as exc:
                message = str(exc)
                result.update(status='failed', error=message)
                key = (trial['host'], message)
                failures[key] = failures.get(key, 0) + 1
                if failures[key] >= 2:
                    stopped.add(trial['host'])
        report['trials'].append(result); save()
        print(json.dumps({key: result[key] for key in ('host', 'task', 'language', 'status')}), flush=True)
    report['inputs_unchanged'] = frozen_inputs() == frozen
    report['scored_trials'] = sum(t['status'] == 'scored' for t in report['trials'])
    report['complete'] = report['inputs_unchanged'] and report['scored_trials'] == len(trials)
    save()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--host', action='append', choices=sorted(model_host.CLI_HOSTS), required=True)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--image', default=w.DEFAULT_IMAGE)
    parser.add_argument('--model', action='append', default=[], help='Explicit host=model, repeated for selected hosts')
    args = parser.parse_args(argv)
    try:
        models = {}
        for assignment in args.model:
            host, separator, model = assignment.partition('=')
            if not separator or host in models:
                raise ValueError('Models require unique host=model assignments')
            models[host] = model
        report = run(args.output, args.host, args.timeout, args.image, models=models)
        return 0 if report['complete'] else 2
    except (ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc)})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
