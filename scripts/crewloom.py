#!/usr/bin/env python3
"""Repository-native Crewloom discovery, validation, and context CLI."""
import argparse
import json
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / '.agents' / 'skills'


def log_run(tool, skill, code, seconds, project=None):
    """Append one run record so the dashboard can show CLI runs live; never fail the run."""
    project = Path(project or Path.cwd()).resolve()
    run_log = project / '.crewloom' / 'runs.jsonl'
    record = {'project_root': str(project), 'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'tool': tool,
              'skill': skill, 'exit_code': code, 'duration_ms': round(seconds * 1000), 'source': 'cli'}
    if os.environ.get('CREWLOOM_NO_LOG'):
        return
    try:
        run_log.parent.mkdir(exist_ok=True)
        with run_log.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record) + '\n')
    except OSError:
        pass


def load_validator():
    path = SKILLS / 'skill-forge-recruiter' / 'scripts' / 'validate_skill.py'
    spec = importlib.util.spec_from_file_location('crewloom_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOST_DIRS = {'claude': Path('.claude') / 'skills', 'agents': Path('.agents') / 'skills'}
SKILL_ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def install_skills(target, host, names, force):
    """Copy role folders into a project's host skill directory; returns (installed, errors)."""
    available = sorted(p.parent.name for p in SKILLS.glob('*/SKILL.md'))
    wanted = names or available
    errors = [f'Unknown skill: {n}' for n in wanted if n not in available]
    if errors:
        return [], errors
    if not target.is_dir():
        return [], [f'Target directory does not exist: {target}']
    destination = target / HOST_DIRS[host]
    clashes = [n for n in wanted if (destination / n).exists()]
    if clashes and not force:
        return [], [f'Already installed (use --force to overwrite): {", ".join(clashes)}']
    for candidate in [destination, *[destination / n for n in wanted]]:
        if not candidate.resolve().is_relative_to(target.resolve()):
            return [], [f'Install path escapes project through a symlink: {candidate}']
        if candidate.is_symlink():
            return [], [f'Refusing symlink install destination: {candidate}']
    # Validate every copied destination before any role is changed.
    for name in wanted:
        for source in (SKILLS / name).rglob('*'):
            relative = source.relative_to(SKILLS / name)
            candidate = destination / name / relative
            if not candidate.resolve().is_relative_to(target.resolve()):
                return [], [f'Install file escapes project through a symlink: {candidate}']
    destination.mkdir(parents=True, exist_ok=True)
    for name in wanted:
        role = destination / name
        shutil.copytree(SKILLS / name, role, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'brain'))
        brain = role / 'brain'
        brain.mkdir(exist_ok=True)
        for filename in ('ARCHITECTURE', 'COMPLETED', 'CHALLENGES', 'IDEAS_VAULT', 'ROADMAP_TODO'):
            memory = brain / (filename + '.md')
            if memory.exists():
                continue
            if filename == 'ARCHITECTURE':
                shutil.copyfile(SKILLS / name / 'brain' / 'ARCHITECTURE.md', memory)
            else:
                memory.write_text(f'# {filename.replace("_", " ").title()}\n\nNo project-specific entries recorded yet.\n', encoding='utf-8')
    return wanted, []


def run_dashboard(port, project):
    folder = ROOT / 'dashboard'
    npm = shutil.which('npm')
    if not npm:
        print('npm not found: install Node 20+ to use the dashboard', file=sys.stderr)
        return 1
    if not (folder / 'node_modules').is_dir():
        code = subprocess.run([npm, 'install', '--no-audit', '--no-fund'], cwd=folder, check=False).returncode
        if code:
            return code
    env = {**os.environ, 'CREWLOOM_ROOT': str(ROOT), 'CREWLOOM_PROJECT': str(project)}
    return subprocess.run([npm, 'run', 'dev', '--', '-p', str(port)], cwd=folder, env=env, check=False).returncode


PATH_FLAGS = {'--project-dir', '--file', '--config', '--packet', '--snapshot', '--tokens', '--out', '--exceptions', '--project'}
POSITIONAL_PATH_TOOLS = {'workflow-contract', 'delivery-evidence'}


def validate_project_paths(tool, arguments, project):
    """Resolve registered input/output path arguments against one project root."""
    paths = []
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        flag, separator, value = arg.partition('=')
        if flag in PATH_FLAGS:
            if not separator:
                index += 1
                if index >= len(arguments):
                    raise ValueError(f'Missing path for {flag}')
                value = arguments[index]
            paths.append(value)
        elif index == 0 and tool in POSITIONAL_PATH_TOOLS and not arg.startswith('-'):
            paths.append(arg)
        index += 1
    for value in paths:
        resolved = (project / value).resolve()
        if not resolved.is_relative_to(project):
            raise ValueError(f'Path escapes selected project: {value}')


def main():
    if not SKILLS.is_dir():
        print('Crewloom needs a repository checkout; install with `pip install -e .` from a clone.', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List available skill IDs')
    evaluation = commands.add_parser('evaluate', help='Score a Unicode feature submission with held-out acceptance')
    evaluation.add_argument('--project', required=True)
    evaluation.add_argument('--image', default='python:3.14-slim')
    evaluation.add_argument('--repeats', type=int, default=3)
    trials = commands.add_parser('evaluate-hosts', help='Collect model artifacts and grade anonymized submissions')
    trials.add_argument('--output', required=True)
    trials.add_argument('--host', choices=('codex', 'claude'), action='append', required=True)
    trials.add_argument('--repeats', type=int, default=5)
    trials.add_argument('--seed', type=int, default=20261001)
    trials.add_argument('--image', default='python:3.14-slim')
    trials.add_argument('--timeout', type=int, default=180)
    trials.add_argument('--codex-model'); trials.add_argument('--claude-model')
    workflow = commands.add_parser('workflow', help='Run an isolated, resumable project workflow')
    workflow.add_argument('workflow_arguments', nargs=argparse.REMAINDER)
    commands.add_parser('tools', help='List included executable tools')
    run = commands.add_parser('run', help='Run a registered local tool')
    run.add_argument('--project', default='.', help='Project root for relative inputs and run history')
    run.add_argument('tool')
    run.add_argument('arguments', nargs=argparse.REMAINDER)
    show = commands.add_parser('show', help='Print a skill procedure')
    show.add_argument('skill')
    validate = commands.add_parser('validate', help='Validate one or all skill structures')
    validate.add_argument('--skill')
    context = commands.add_parser('context', help='Build a bounded context pack')
    context.add_argument('--project', help='Use only this project’s installed roles and memory')
    context.add_argument('skill')
    context.add_argument('--out', required=True)
    context.add_argument('--language', choices=('en', 'ar'), default='en')
    install = commands.add_parser('install', help='Copy roles into a project for your agent host')
    install.add_argument('--host', choices=sorted(HOST_DIRS), required=True,
                         help='claude -> .claude/skills, agents -> .agents/skills')
    install.add_argument('--target', default='.', help='Project directory (default: current)')
    install.add_argument('--skill', action='append', default=[], help='Role ID; repeat for several (default: all)')
    install.add_argument('--force', action='store_true', help='Overwrite roles that already exist')
    dash = commands.add_parser('dashboard', help='Start the live dashboard (needs Node 20+)')
    dash.add_argument('--project', default='.', help='Project monitored by this dashboard process')
    dash.add_argument('--port', type=int, default=4317)
    args = parser.parse_args()
    if args.command == 'evaluate':
        from evaluate_feature import main as evaluate_main
        return evaluate_main(['--project', args.project, '--image', args.image, '--repeats', str(args.repeats)])
    if args.command == 'evaluate-hosts':
        from evaluate_hosts import main as trials_main
        forwarded = ['--output', args.output, '--repeats', str(args.repeats), '--seed', str(args.seed), '--image', args.image, '--timeout', str(args.timeout)]
        for host in args.host: forwarded.extend(['--host', host])
        for host in ('codex', 'claude'):
            model = getattr(args, host + '_model')
            if model: forwarded.extend(['--' + host + '-model', model])
        return trials_main(forwarded)
    if args.command == 'workflow':
        from workflow import main as workflow_main
        return workflow_main(args.workflow_arguments)
    project = Path(getattr(args, 'project', None) or '.').resolve()
    if not project.is_dir():
        parser.error('Project root must be an existing directory')
    if args.command == 'dashboard':
        return run_dashboard(args.port, project)
    if args.command == 'install':
        for name in args.skill:
            if not SKILL_ID.fullmatch(name):
                parser.error(f'Invalid skill ID: {name}')
        installed, errors = install_skills(Path(args.target).resolve(), args.host, args.skill, args.force)
        for error in errors:
            print(error, file=sys.stderr)
        if errors:
            return 2
        print(f'Installed {len(installed)} roles into {Path(args.target).resolve() / HOST_DIRS[args.host]}')
        return 0
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
        try:
            if any(not candidate.resolve().is_relative_to(project) for candidate in (project / '.crewloom', project / '.crewloom/runs.jsonl')):
                raise ValueError('Run history directory escapes selected project')
            validate_project_paths(item['id'], arguments, project)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        if item['id'] == 'context' and project != ROOT and '--project' not in arguments:
            arguments = ['--project', str(project), *arguments]
        started = time.monotonic()
        code = subprocess.run([sys.executable, str(path), *arguments], cwd=project, check=False).returncode
        log_run(item['id'], item['skill'], code, time.monotonic() - started, project)
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
    context_args = [sys.executable, str(script), '--skill', name, '--out', args.out, '--language', args.language]
    if args.project:
        context_args += ['--project', str(project)]
    return subprocess.run(context_args, cwd=project, check=False).returncode


if __name__ == '__main__':
    sys.exit(main())
