#!/usr/bin/env python3
"""Repository-native Crewloom discovery, validation, and context CLI."""
import argparse
import json
import importlib.util
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import crewloom_resources as resources
from crewloom_resources import ResourceError

LOOPBACK = ('127.0.0.1', '::1', 'localhost')


def library_root():
    """Root that holds role trees and documentation for this installation."""
    return resources.distribution_root()


def skills_dir():
    """Directory holding the 42 role trees for this installation."""
    return resources.roles_dir()


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



def run_registered(item, path, arguments, project):
    """Bound a noninteractive catalog invocation and retain project-local execution receipts.

    The runner enforces declared wall time and combined output bytes, acknowledges
    process identity before target dispatch, and cleans cooperating descendants.
    Described effects/capabilities remain metadata; this is a native process boundary.
    """
    import admission
    import continuation
    import project_binding
    import tool_catalog
    import workflow as w
    timeout = item.get('limits', {}).get('timeout_seconds', 600)
    output_limit = item.get('limits', {}).get('output_bytes', 1048576)
    if type(timeout) is not int or timeout < 1 or type(output_limit) is not int or output_limit < 1:
        raise ValueError('Tool execution limits must be positive integers')
    operation = uuid.uuid4().hex
    project = Path(project).resolve()
    validate_project_paths(item['id'], arguments, project, item.get('inputs'))
    # Reuse the existing privacy writer; payloads stay ignored even in a first-use project.
    folder = w.safe_path(project, '.crewloom/tools/' + item['id'] + '/' + operation, internal=True)
    project_binding.preflight(project, ['.gitignore', str(folder.relative_to(project))])
    project_binding.ignore_local_state(project)
    admission.configure(folder, operation, {})
    receipt_path = folder / 'execution.json'
    provenance = tool_catalog.provenance(item, resources.distribution_root())
    record = {'schema_version': 1, 'operation_id': operation, 'tool': item['id'],
              'project_root': str(project), 'source_sha256': provenance['source'],
              'contract_sha256': provenance['contract'], 'support_sha256': provenance['support'],
              'started_at': datetime.now(timezone.utc).isoformat(), 'state': 'intent',
              'limits': {'timeout_seconds': timeout, 'output_bytes': output_limit},
              'boundary': 'native managed process; declared effects are not a filesystem/network sandbox',
              'acceptance': 'tool execution receipt only; application acceptance is separate'}
    def save():
        continuation._private_write(receipt_path, json.dumps(record, indent=2))
    save()  # Required before target side effects; never fall back to silent best effort.
    with admission.context(folder, item['id']):
        process = admission.launch_owned([sys.executable, str(path), *arguments], cwd=project,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, bufsize=0)
        process.stdin.close()
        count = [0]; exceeded = threading.Event(); read_error = threading.Event(); stop_reading = threading.Event()
        def collect():
            try:
                while not stop_reading.is_set():
                    chunk = process.stdout.read(8192)
                    if not chunk or stop_reading.is_set(): break
                    allowed = max(0, output_limit - count[0]); count[0] += len(chunk)
                    if len(chunk) > allowed: exceeded.set()
                    if allowed:
                        sink = getattr(sys.stdout, 'buffer', None)
                        if sink is not None: sink.write(chunk[:allowed]); sink.flush()
                        else: sys.stdout.write(chunk[:allowed].decode('utf-8', 'replace')); sys.stdout.flush()
            except (OSError, ValueError):
                if not stop_reading.is_set(): read_error.set()
            finally:
                process.stdout.close()
        reader = threading.Thread(target=collect, daemon=True); reader.start()
        started = time.monotonic(); reason = None
        try:
            while process.poll() is None:
                if exceeded.is_set(): reason = 'output-limit'; break
                if read_error.is_set(): reason = 'output-reader-failed'; break
                if time.monotonic() - started >= timeout: reason = 'timeout'; break
                time.sleep(0.02)
        finally:
            try: cleanup = admission.settle_current_process(process.pid)
            except (OSError, ValueError, admission.AdmissionError) as exc:
                cleanup = 'unverifiable: cleanup raised ' + type(exc).__name__
            if cleanup in ('gone', 'terminated', 'killed'):
                if process.poll() is None:
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: cleanup = 'unverifiable: process did not settle'
                reader.join(timeout=5)
            # The reader closes its own raw pipe after its pending read settles.
            # Closing a pipe from another thread can wait on platform I/O locks.
            # Request cancellation; retain unknown ownership for explicit recovery.
            stop_reading.set()
            if not reader.is_alive(): process.stdout.close()
        if exceeded.is_set(): reason = 'output-limit'
        if read_error.is_set() or reader.is_alive(): reason = 'output-reader-failed'
        if cleanup not in ('gone', 'terminated', 'killed'): reason = 'cleanup-unverified'
        code = 124 if reason == 'timeout' else 2 if reason else process.returncode
        record.update(state='unsettled' if cleanup not in ('gone', 'terminated', 'killed') else 'finished',
                      exit_code=code, reason=reason, cleanup=cleanup, process_exit_code=process.poll(),
                      output_bytes_observed=count[0], output_complete=not bool(reason),
                      duration_ms=round((time.monotonic()-started)*1000))
        save()
        if reason: print('Tool execution stopped: ' + reason, file=sys.stderr)
        return code


def load_validator():
    path = resources.require('.agents/skills/skill-forge-recruiter/scripts/validate_skill.py',
                            'Role structure validator')
    spec = importlib.util.spec_from_file_location('crewloom_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOST_DIRS = {'claude': Path('.claude') / 'skills', 'agents': Path('.agents') / 'skills'}
SKILL_ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def install_skills(target, host, names, force):
    """Copy role folders into a project's host skill directory; returns (installed, errors)."""
    source_root = resources.roles_dir()
    available = resources.role_ids()
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
        for source in (source_root / name).rglob('*'):
            relative = source.relative_to(source_root / name)
            candidate = destination / name / relative
            if not candidate.resolve().is_relative_to(target.resolve()):
                return [], [f'Install file escapes project through a symlink: {candidate}']
    # Consumer memory/configuration is local state, while the library keeps public templates.
    import project_binding
    try:
        local_memory = not project_binding.library_source(target)
        private = project_binding.tracked_private_paths(target, role_memory=local_memory)
        if private:
            return [], ['Private project data is already tracked; remove it from this project '
                        'index while preserving local files: ' + ', '.join(private[:20])]
        project_binding.ignore_local_state(target, role_memory=local_memory)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return [], [str(exc)]
    destination.mkdir(parents=True, exist_ok=True)
    for name in wanted:
        role = destination / name
        shutil.copytree(source_root / name, role, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'brain'))
        brain = role / 'brain'
        brain.mkdir(exist_ok=True)
        for filename in ('ARCHITECTURE', 'COMPLETED', 'CHALLENGES', 'IDEAS_VAULT', 'ROADMAP_TODO'):
            memory = brain / (filename + '.md')
            if memory.exists():
                continue
            if filename == 'ARCHITECTURE':
                shutil.copyfile(source_root / name / 'brain' / 'ARCHITECTURE.md', memory)
            else:
                memory.write_text(f'# {filename.replace("_", " ").title()}\n\nNo project-specific entries recorded yet.\n', encoding='utf-8')
    return wanted, []


MIN_DASHBOARD_TOKEN = 32


def dashboard_token():
    """Server-only dashboard secret: environment in, environment out, never an argument.

    A value shorter than the generated secret is refused rather than accepted. A short
    "password" that authorizes project reads and tool runs is not meaningfully different
    from no authentication, so the server treats it as unconfigured.
    """
    configured = os.environ.get('CREWLOOM_DASHBOARD_TOKEN', '').strip()
    return configured if len(configured) >= MIN_DASHBOARD_TOKEN else None


def write_dashboard_secret(project, token):
    """Publish the generated login secret to an owner-only file, never to stdout.

    A printed secret reaches scrollback, terminal scrollback, CI logs, and every process
    that captures this process's output. The file lives in the project's runtime directory
    with mode 0600, so only the owner can read it, and only its path is printed. The
    temporary file is created exclusively under a random name: a predictable name would let
    a pre-planted symlink redirect a secret write into another project.
    """
    path = project / '.crewloom' / 'dashboard-token'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Refusing a symlinked dashboard credential path: ' + str(path))
    descriptor, name = tempfile.mkstemp(dir=str(path.parent), prefix='dashboard-token.', suffix='.tmp')
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(token + '\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    os.chmod(path, 0o600)
    return path


def dashboard_binding_allowed(hostname):
    """A non-loopback interface is refused unless authentication was configured explicitly."""
    return hostname in LOOPBACK or dashboard_token() is not None


def run_dashboard(port, project, hostname):
    """Start the authenticated dashboard, or explain exactly what is missing."""
    try:
        folder = resources.dashboard_dir()
    except ResourceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    npm = shutil.which('npm')
    if not npm:
        print('npm not found: install Node 20+ to use the dashboard', file=sys.stderr)
        return 1
    if not dashboard_binding_allowed(hostname):
        print('Refusing a non-loopback dashboard bind without configured authentication. '
              f'Set CREWLOOM_DASHBOARD_TOKEN to at least {MIN_DASHBOARD_TOKEN} characters, or '
              'keep the default 127.0.0.1.', file=sys.stderr)
        return 2
    token = dashboard_token()
    generated = token is None
    if generated:
        token = secrets.token_urlsafe(32)
    if not (folder / 'node_modules').is_dir():
        code = subprocess.run([npm, 'install', '--no-audit', '--no-fund'], cwd=folder, check=False).returncode
        if code:
            return code
    # The token travels in the child environment only: never an argument, so it stays out of
    # process listings, access logs, browser history, and the selected project's run records.
    env = {**os.environ, 'CREWLOOM_ROOT': str(library_root()), 'CREWLOOM_PROJECT': str(project),
           'CREWLOOM_DASHBOARD_TOKEN': token, 'CREWLOOM_DASHBOARD_PORT': str(port),
           'CREWLOOM_DASHBOARD_HOST': hostname}
    if generated:
        try:
            secret = write_dashboard_secret(project, token)
        except OSError as exc:
            print(f'Could not write the dashboard credential file: {exc}', file=sys.stderr)
            return 2
        print(f'Dashboard access token written to {secret} (owner-only).')
    print(f'Open http://{hostname}:{port} and paste that token into the sign-in box.')
    return subprocess.run([npm, 'run', 'dev', '--', '-H', hostname, '-p', str(port)],
                          cwd=folder, env=env, check=False).returncode


def read_tools():
    """The runtime tool registry, read from installed resources rather than the checkout."""
    registry = resources.require('documentation/TOOLS.json', 'Tool registry')
    value = json.loads(registry.read_text(encoding='utf-8'))
    tools = value.get('tools') if isinstance(value, dict) else None
    if not isinstance(tools, list) or not tools or any(not isinstance(item, dict) or 'id' not in item or 'path' not in item for item in tools):
        raise ValueError('Malformed tool registry: ' + str(registry))
    return tools


def tool_path(item):
    """Resolve a registered tool inside this installation, never outside it."""
    path = resources.resolve(item['path']).resolve()
    roots = [root.resolve() for root in resources.installed_roots()]
    if not any(root == path or root in path.parents for root in roots) or not path.is_file():
        raise ValueError('Tool path is missing or escapes the installed resources: ' + str(item['path']))
    return path


PATH_FLAGS = {'--project-dir', '--file', '--config', '--packet', '--snapshot', '--tokens', '--out', '--exceptions',
              '--project', '--project-root', '--root', '--plan', '--manifest', '--output', '--index-file'}
POSITIONAL_PATH_TOOLS = {'workflow-contract', 'delivery-evidence'}

# Commands whose parser, defaults and exit codes live in another module. They declare no arguments
# here on purpose: the caller's argv is forwarded untouched, so a new flag on the child needs no
# change here and cannot be silently dropped by an intermediate list of arguments to keep in step.
DELEGATED = {'host': 'host_lifecycle', 'readiness': 'agency_readiness', 'continuation': 'continuation'}
STUDY_ARGUMENTS = ('context', 'study')


def delegated_command(argv):
    """The `(module, argv)` a public command hands to its owning module, or ``None``.

    `host`, `readiness` and `context study` are decided before this file's own parser runs, because
    `argparse.REMAINDER` cannot forward a flag. A remainder placeholder only captures the tokens
    that follow the first non-option word, so `crewloom readiness --project-id X` — the whole
    documented shape of a command that has no subcommand — would be refused here with
    "unrecognized arguments", and `crewloom host --help` would print a usage line naming no option
    at all instead of the host lifecycle commands that actually exist.

    The forwarded argv is exactly the argv the caller typed. Nothing is inspected, rewritten or
    reordered, so the owning module keeps its own usage text, defaults and refusal messages, and
    this file can never grow a stale copy of them.
    """
    if tuple(argv[:2]) == STUDY_ARGUMENTS:
        # `evaluate_hosts.main` is the single real entry point for both collection modes. It
        # recognizes `--study` itself and hands over to the study collector, so this command and
        # the legacy `evaluate-hosts` invocation are one code path rather than two parsers that
        # can drift apart. Nothing is dropped and no existing flag changes meaning.
        return 'evaluate_hosts', ['--study', *argv[2:]]
    if argv and argv[0] in DELEGATED:
        return DELEGATED[argv[0]], list(argv[1:])
    return None


def validate_project_paths(tool, arguments, project, inputs=None):
    """Resolve registered input/output path arguments against one project root."""
    paths = []
    roots = []
    path_flags = PATH_FLAGS | {name for name, value in (inputs or {}).items()
                              if name.startswith('--') and isinstance(value, dict) and value.get('type') == 'path'}
    # These two registered readiness inputs are explicit read-only external references.
    if tool == 'agency-readiness': path_flags -= {'--agency-root', '--registry'}
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        flag, separator, value = arg.partition('=')
        if flag.startswith('--') and flag not in path_flags and any(name.startswith(flag) for name in path_flags):
            raise ValueError('Abbreviated path flags are forbidden; use the complete declared flag')
        if flag in path_flags:
            if not separator:
                index += 1
                if index >= len(arguments):
                    raise ValueError(f'Missing path for {flag}')
                value = arguments[index]
            paths.append(value)
            if flag in ('--project', '--project-root', '--root'): roots.append(value)
        elif index == 0 and tool in POSITIONAL_PATH_TOOLS and not arg.startswith('-'):
            paths.append(arg)
        index += 1
    for value in paths:
        resolved = (project / value).resolve()
        if not resolved.is_relative_to(project):
            raise ValueError(f'Path escapes selected project: {value}')
    for value in roots:
        if (project / value).resolve() != project:
            raise ValueError('Project/root selectors must equal the selected canonical root, not a nested project')
    if tool == 'tool-catalog' and any(arg in ('render', 'record-evidence') for arg in arguments) \
            and not roots and resources.distribution_root().resolve() != project:
        raise ValueError('Catalog mutation needs the selected toolkit root or an explicit matching --root; consumer runs cannot modify the installed library')


def main():
    try:
        resources.layout()
    except ResourceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    arguments = sys.argv[1:]
    handed_over = delegated_command(arguments)
    if handed_over is not None:
        module, argv = handed_over
        return importlib.import_module(module).main(argv)
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
    mapping=commands.add_parser('map',help='Build a bounded project symbol map')
    mapping.add_argument('--project',required=True)
    mapping.add_argument('--query',default='')
    mapping.add_argument('--budget',type=int,default=8192)
    mapping.add_argument('--seed',action='append',default=[])
    mapping.add_argument('--rebuild',action='store_true',help='Discard cached parses and re-index every candidate')
    project = commands.add_parser('project', help='Enter, inspect, finish, cancel or relink a bound project context')
    project.add_argument('project_arguments', nargs=argparse.REMAINDER)
    lesson = commands.add_parser('lesson', help='Record, verify, retrieve or review project lessons')
    lesson.add_argument('lesson_arguments', nargs=argparse.REMAINDER)
    workflow = commands.add_parser('workflow', help='Run an isolated, resumable project workflow')
    workflow.add_argument('workflow_arguments', nargs=argparse.REMAINDER)
    capabilities = commands.add_parser('capabilities', help='Show a host/model capability profile with the evidence basis of each fact')
    capabilities.add_argument('--host', required=True)
    capabilities.add_argument('--model')
    capabilities.add_argument('--launch-mode', choices=('managed-generation', 'native-interactive'))
    capabilities.add_argument('--project', help='Also store the profile in this project\'s private .crewloom/capabilities')
    source = commands.add_parser('source', help='Show which Crewloom is running: version, roots, revision, dirty state')
    source.add_argument('--json', action='store_true', help='Machine-readable output')
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
    # `host` and `readiness` are registered so `crewloom --help` and the usage line list them.
    # They take no arguments here: `delegated_command` hands their whole argv to the owning module
    # before this parser runs, which is the only way a flag can survive the hand-over.
    commands.add_parser('host', help='Install, observe, guard and verify native host callbacks')
    commands.add_parser('continuation', help='Durable checkpoints for continuing a task with another agent (create, validate, accept, interrupt, reconcile)')
    commands.add_parser('readiness', help='Read-only rollout readiness for one registered project')
    install = commands.add_parser('install', help='Copy roles into a project for your agent host')
    install.add_argument('--host', choices=sorted(HOST_DIRS), required=True,
                         help='claude -> .claude/skills, agents -> .agents/skills')
    install.add_argument('--target', default='.', help='Project directory (default: current)')
    install.add_argument('--skill', action='append', default=[], help='Role ID; repeat for several (default: all)')
    install.add_argument('--force', action='store_true', help='Overwrite roles that already exist')
    dash = commands.add_parser('dashboard', help='Start the live dashboard (needs Node 20+)')
    dash.add_argument('--project', default='.', help='Project monitored by this dashboard process')
    dash.add_argument('--port', type=int, default=4317)
    dash.add_argument('--host', default='127.0.0.1',
                      help='Interface to bind; a non-loopback value requires configured authentication')
    reviewer = commands.add_parser('reviewer', help='Manage credential-verified reviewer identities')
    reviewer.add_argument('reviewer_arguments', nargs=argparse.REMAINDER)
    coordinator = commands.add_parser('coordinator', help='Run a concurrent, reviewed DAG of isolated project worktrees')
    coordinator.add_argument('coordinator_arguments', nargs=argparse.REMAINDER)
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
    if args.command == 'map':
        from repo_map import main as map_main
        return map_main(['--project',args.project,'--query',args.query,'--budget',str(args.budget)]
                        + sum([['--seed',seed] for seed in args.seed],[])
                        + (['--rebuild'] if args.rebuild else []))
    if args.command == 'project':
        from project_binding import main as project_main
        return project_main(args.project_arguments)
    if args.command == 'lesson':
        from project_lessons import main as lesson_main
        return lesson_main(args.lesson_arguments)
    if args.command == 'workflow':
        from workflow import main as workflow_main
        return workflow_main(args.workflow_arguments)
    if args.command == 'reviewer':
        from reviewer_credentials import main as reviewer_main
        return reviewer_main(args.reviewer_arguments)
    if args.command == 'coordinator':
        from task_coordinator import main as coordinator_main
        return coordinator_main(args.coordinator_arguments)
    if args.command == 'capabilities':
        import model_host
        info, note = None, None
        if args.host in model_host.CLI_HOSTS:
            try:
                info = model_host.probe(args.host)
            except (model_host.HostUnavailable, OSError, subprocess.SubprocessError) as exc:
                note = 'host not probed: ' + str(exc)
        try:
            profile = model_host.capability_profile(args.host, args.model, args.launch_mode, info)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if note:
            profile['note'] = note
        if args.project:
            import workflow as w
            root = Path(args.project).resolve()
            target = w.safe_path(root, '.crewloom/capabilities/' + args.host + '.json', internal=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            profile['stored'] = str(target)
        print(json.dumps(profile, indent=2, ensure_ascii=False))
        return 0
    if args.command == 'source':
        identity = resources.source_identity()
        if args.json:
            print(json.dumps(identity, indent=2, ensure_ascii=False))
        else:
            for key, value in identity.items():
                print(f"{key:21} {'unknown' if value is None else value}")
        return 0
    project = Path(getattr(args, 'project', None) or '.').resolve()
    if not project.is_dir():
        parser.error('Project root must be an existing directory')
    if args.command == 'dashboard':
        return run_dashboard(args.port, project, args.host)
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
        tools = read_tools()
        if args.command == 'tools':
            for item in tools:
                print(f"{item['id']:20} {item['description']}")
            return 0
        item = next((item for item in tools if item['id'] == args.tool), None)
        if item is None:
            parser.error('Unknown registered tool')
        try:
            path = tool_path(item)
        except (ResourceError, ValueError) as exc:
            parser.error(str(exc))
        arguments = args.arguments[1:] if args.arguments and args.arguments[0] == '--' else args.arguments
        import tool_catalog
        allowed, notice = tool_catalog.execution_decision(item, resources.distribution_root(), path)
        if not allowed:
            parser.error(notice)
        if notice:
            print('warning: ' + notice, file=sys.stderr)
        try:
            if any(not candidate.resolve().is_relative_to(project) for candidate in (project / '.crewloom', project / '.crewloom/runs.jsonl')):
                raise ValueError('Run history directory escapes selected project')
            validate_project_paths(item['id'], arguments, project, item.get('inputs'))
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        if item['id'] == 'context' and project != resources.distribution_root() and '--project' not in arguments:
            arguments = ['--project', str(project), *arguments]
        started = time.monotonic()
        try:
            code = (run_registered(item, path, arguments, project) if item.get('contract_version') else
                    subprocess.run([sys.executable, str(path), *arguments], cwd=project, check=False).returncode)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print('Tool execution refused or interrupted: ' + str(exc), file=sys.stderr)
            return 2
        log_run(item['id'], item['skill'], code, time.monotonic() - started, project)
        return code
    if args.command == 'list':
        for ident in resources.role_ids():
            print(ident)
        return 0
    name = getattr(args, 'skill', None)
    if name and not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        parser.error('Invalid skill ID')
    if name:
        try:
            role = resources.role_dir(name)
        except ResourceError:
            parser.error('Unknown skill ID')
    if args.command == 'show':
        print((role / 'SKILL.md').read_text(encoding='utf-8'))
        return 0
    if args.command == 'validate':
        validator = load_validator()
        names = [name] if name else resources.role_ids()
        failures = {ident: validator.check(ident) for ident in names}
        failures = {ident: errors for ident, errors in failures.items() if errors}
        for ident, errors in failures.items():
            print(f'FAIL {ident}: {errors}', file=sys.stderr)
        if not failures:
            print(f'PASS: {len(names)} skills')
        return 1 if failures else 0
    script = resources.require('.agents/skills/context-guardian/scripts/context_pack.py',
                              'Context pack generator')
    context_args = [sys.executable, str(script), '--skill', name, '--out', args.out, '--language', args.language]
    if args.project:
        context_args += ['--project', str(project)]
    return subprocess.run(context_args, cwd=project, check=False).returncode


if __name__ == '__main__':
    sys.exit(main())
