#!/usr/bin/env python3
"""Repository-native Crewloom discovery, validation, and context CLI."""
import argparse
import json
import importlib.util
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / '.agents' / 'skills'
RUN_LOG = ROOT / '.crewloom' / 'runs.jsonl'


def log_run(tool, skill, code, seconds):
    """Append one run record so the dashboard can show CLI runs live; never fail the run."""
    record = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'tool': tool,
              'skill': skill, 'exit_code': code, 'duration_ms': round(seconds * 1000), 'source': 'cli'}
    if os.environ.get('CREWLOOM_NO_LOG'):
        return
    try:
        RUN_LOG.parent.mkdir(exist_ok=True)
        with RUN_LOG.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record) + '\n')
    except OSError:
        pass


def load_validator():
    path = SKILLS / 'skill-forge-recruiter' / 'scripts' / 'validate_skill.py'
    spec = importlib.util.spec_from_file_location('crewloom_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List available skill IDs')
    commands.add_parser('tools', help='List included executable tools')
    run = commands.add_parser('run', help='Run a registered local tool')
    run.add_argument('tool')
    run.add_argument('arguments', nargs=argparse.REMAINDER)
    show = commands.add_parser('show', help='Print a skill procedure')
    show.add_argument('skill')
    validate = commands.add_parser('validate', help='Validate one or all skill structures')
    validate.add_argument('--skill')
    context = commands.add_parser('context', help='Build a bounded context pack')
    context.add_argument('skill')
    context.add_argument('--out', required=True)
    context.add_argument('--language', choices=('en', 'ar'), default='en')
    args = parser.parse_args()
    if args.command in ('tools', 'run'):
        tools = json.loads((ROOT / 'documentation' / 'TOOLS.json').read_text())['tools']
        if args.command == 'tools':
            for item in tools:
                print(f"{item['id']:20} {item['description']}")
            return 0
        item = next((item for item in tools if item['id'] == args.tool), None)
        if item is None:
            parser.error('Unknown registered tool')
        path = (ROOT / item['path']).resolve()
        if ROOT not in path.parents or not path.is_file():
            parser.error('Tool path is missing or escapes the repository')
        arguments = args.arguments[1:] if args.arguments and args.arguments[0] == '--' else args.arguments
        started = time.monotonic()
        code = subprocess.run([sys.executable, str(path), *arguments], check=False).returncode
        log_run(item['id'], item['skill'], code, time.monotonic() - started)
        return code
    if args.command == 'list':
        for path in sorted(SKILLS.glob('*/SKILL.md')):
            print(path.parent.name)
        return 0
    name = getattr(args, 'skill', None)
    if name and not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        parser.error('Invalid skill ID')
    if name and not (SKILLS / name / 'SKILL.md').is_file():
        parser.error('Unknown skill ID')
    if args.command == 'show':
        print((SKILLS / name / 'SKILL.md').read_text(encoding='utf-8'))
        return 0
    if args.command == 'validate':
        validator = load_validator()
        names = [name] if name else [p.parent.name for p in sorted(SKILLS.glob('*/SKILL.md'))]
        failures = {ident: validator.check(ident) for ident in names}
        failures = {ident: errors for ident, errors in failures.items() if errors}
        for ident, errors in failures.items():
            print(f'FAIL {ident}: {errors}', file=sys.stderr)
        if not failures:
            print(f'PASS: {len(names)} skills')
        return 1 if failures else 0
    script = SKILLS / 'context-guardian' / 'scripts' / 'context_pack.py'
    return subprocess.run([sys.executable, str(script), '--skill', name, '--out', args.out,
                           '--language', args.language], check=False).returncode


if __name__ == '__main__':
    sys.exit(main())
