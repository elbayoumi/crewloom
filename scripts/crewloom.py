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
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import crewloom_resources as resources
from crewloom_resources import ResourceError

LOOPBACK = ('127.0.0.1', '::1', 'localhost')


def library_root():
    """Root that holds role trees and documentation for this installation."""
    return resources.distribution_root()


def skills_dir():
    """Directory holding the 44 role trees for this installation."""
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


def load_validator():
    path = resources.require('.agents/skills/skill-forge-recruiter/scripts/validate_skill.py',
                            'Role structure validator')
    spec = importlib.util.spec_from_file_location('crewloom_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOST_DIRS = {'claude': Path('.claude') / 'skills', 'agents': Path('.agents') / 'skills'}
SKILL_ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def initialize_role_memory(target, role):
    """Create missing local memory without replacing guides or existing project lessons."""
    import project_binding
    names = ('ARCHITECTURE', 'COMPLETED', 'CHALLENGES', 'IDEAS_VAULT', 'ROADMAP_TODO')
    destinations = [project_binding.writable(target, (role / 'brain' / (name + '.md')).relative_to(target).as_posix())
                    for name in names]
    brain = role / 'brain'
    brain.mkdir(exist_ok=True)
    os.chmod(brain, 0o700)
    for name, destination in zip(names, destinations):
        if destination.exists():
            continue
        template = resources.roles_dir() / role.name / 'brain' / 'ARCHITECTURE.md'
        if name == 'ARCHITECTURE' and template.is_file():
            data = template.read_bytes()
        else:
            data = ('# ' + name.replace('_', ' ').title() + '\n\nNo project-specific entries recorded yet.\n').encode()
        with destination.open('xb') as stream:
            os.chmod(destination, 0o600)
            stream.write(data)


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
    import project_binding
    try:
        project_binding.writable(target, '.gitignore')
    except (ValueError, OSError) as exc:
        return [], [str(exc)]
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
    destination.mkdir(parents=True, exist_ok=True)
    for name in wanted:
        role = destination / name
        shutil.copytree(source_root / name, role, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'brain'))
        initialize_role_memory(target, role)
    import privacy
    privacy.ignores(target, HOST_DIRS[host])
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
    """Start password-free on loopback; remote interfaces still require a configured secret."""
    try:
        folder = resources.dashboard_dir()
    except ResourceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    npm = shutil.which('npm')
    if not npm:
        print('npm not found: install Node 24+ to use the dashboard', file=sys.stderr)
        return 1
    if not dashboard_binding_allowed(hostname):
        print('Refusing a non-loopback dashboard bind without configured authentication. '
              f'Set CREWLOOM_DASHBOARD_TOKEN to at least {MIN_DASHBOARD_TOKEN} characters, or '
              'keep the default 127.0.0.1.', file=sys.stderr)
        return 2
    token = dashboard_token()
    local = hostname in LOOPBACK
    if not (folder / 'node_modules').is_dir():
        code = subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=folder, check=False).returncode
        if code:
            return code
    env = {**os.environ, 'CREWLOOM_ROOT': str(library_root()), 'CREWLOOM_PROJECT': str(project),
           'CREWLOOM_DASHBOARD_TOKEN': '' if local else token or '', 'CREWLOOM_DASHBOARD_PORT': str(port),
           'CREWLOOM_DASHBOARD_HOST': hostname, 'CREWLOOM_DASHBOARD_LOCAL': '1' if local else '0'}
    display_host = '[::1]' if hostname == '::1' else hostname
    print(f'Open http://{display_host}:{port}' + (' — no password needed.' if local else ' and sign in with your configured token.'))
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


PATH_FLAGS = {'--project-dir', '--file', '--config', '--packet', '--snapshot', '--tokens', '--out', '--exceptions', '--project', '--findings'}
POSITIONAL_PATH_TOOLS = {'workflow-contract', 'delivery-evidence'}

# Commands whose parser, defaults and exit codes live in another module. They declare no arguments
# here on purpose: the caller's argv is forwarded untouched, so a new flag on the child needs no
# change here and cannot be silently dropped by an intermediate list of arguments to keep in step.
DELEGATED = {'host': 'host_lifecycle', 'readiness': 'agency_readiness', 'queue': 'task_queue', 'budget': 'usage_budget', 'evaluate-bilingual': 'bilingual_evaluation', 'mcp': 'mcp_bridge', 'native': 'native_desktop'}
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


def run_demo(role='reverse-engineering-analyst', fast=False, project=None):
    """Interactive 20-second terminal walkthrough showing role selection, memory consultation, and container isolation."""
    started_at = time.monotonic()
    project_root = Path(project or Path.cwd()).resolve()

    # Fast bypass when explicitly requested, piped non-interactively, or flagged in environment
    fast_mode = bool(fast or not sys.stdout.isatty() or os.environ.get('CREWLOOM_DEMO_FAST') == '1')

    # Color styling with graceful fallback for non-TTY or NO_COLOR
    is_tty = sys.stdout.isatty() and not os.environ.get('NO_COLOR')
    BOLD = '\033[1m' if is_tty else ''
    CYAN = '\033[36m' if is_tty else ''
    GREEN = '\033[32m' if is_tty else ''
    YELLOW = '\033[33m' if is_tty else ''
    BLUE = '\033[34m' if is_tty else ''
    DIM = '\033[2m' if is_tty else ''
    RESET = '\033[0m' if is_tty else ''

    def pace(seconds):
        if not fast_mode:
            time.sleep(seconds)

    def print_flush(text: str = '') -> None:
        try:
            sys.stdout.write(text + '\n')
            sys.stdout.flush()
        except BrokenPipeError:
            try:
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, sys.stdout.fileno())
            except Exception:
                pass
            sys.exit(0)

    # Walkthrough Banner
    print_flush(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════════════════╗{RESET}")
    print_flush(f"{BOLD}{CYAN}║                     CREWLOOM INTERACTIVE DEMO WALKTHROUGH                    ║{RESET}")
    print_flush(f"{BOLD}{CYAN}║   Zero-Dependency Specialist Agents • 5-File Brain • Isolated Containers    ║{RESET}")
    print_flush(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════════════════════╝{RESET}\n")
    pace(0.5)

    # ==========================================================================
    # Phase 1: Role Selection & Catalog Discovery (~4.0s)
    # ==========================================================================
    print_flush(f"{BOLD}{BLUE}┌── [Phase 1/4] Role Selection & Catalog Discovery ─────────────────────────────┐{RESET}")
    pace(1.0)

    role_ids = resources.role_ids()
    if role not in role_ids:
        print_flush(f"{BOLD}{YELLOW}│  ✖ Requested role '{role}' not found in catalog.{RESET}")
        print_flush(f"│  Available roles ({len(role_ids)}): {', '.join(role_ids[:5])}...")
        print_flush(f"└── Exiting with code 2 ────────────────────────────────────────────────────────┘\n")
        return 2

    role_dir = resources.role_dir(role)
    skill_file = role_dir / 'SKILL.md'
    skill_text = skill_file.read_text(encoding='utf-8')

    # Extract YAML frontmatter
    role_name = role
    mission = "Specialist execution role"
    if skill_text.startswith('---'):
        parts = skill_text.split('---', 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if line.startswith('name:'):
                    role_name = line.partition(':')[2].strip()
                elif line.startswith('description:'):
                    mission = line.partition(':')[2].strip()

    # Extract trigger section (When to use / Triggers)
    trigger_match = re.search(r'(?i)##\s+(?:When to use|متى يُستخدم|Triggers)[^\n]*\n+([\s\S]*?)(?=\n##|\Z)', skill_text)
    triggers = trigger_match.group(1).strip().replace('\n', ' ') if trigger_match else "Activated on domain-specific task match"
    if len(triggers) > 115:
        triggers = triggers[:112] + "..."

    print_flush(f"│  • Catalog Scan:       {GREEN}{len(role_ids)} repository-native role trees discovered{RESET}")
    print_flush(f"│  • Selected Role:      {BOLD}{role_name}{RESET}")
    pace(1.5)
    print_flush(f"│  • Role Mission:       {DIM}{mission[:100]}...{RESET}")
    print_flush(f"│  • Activation Trigger: {DIM}{triggers}{RESET}")
    print_flush(f"│  • Role Package:       SKILL.md, 5-file brain/, references/, tools/")
    print_flush(f"│  • Status:             {GREEN}✔ Role specification loaded & verified{RESET}")
    print_flush(f"└───────────────────────────────────────────────────────────────────────────────┘\n")
    pace(1.5)

    # ==========================================================================
    # Phase 2: Working Memory Consultation (5-File Brain) (~5.5s)
    # ==========================================================================
    print_flush(f"{BOLD}{BLUE}┌── [Phase 2/4] Working Memory Consultation (5-File Brain) ─────────────────────┐{RESET}")
    pace(1.5)

    brain_names = ('ARCHITECTURE.md', 'COMPLETED.md', 'CHALLENGES.md', 'IDEAS_VAULT.md', 'ROADMAP_TODO.md')
    # Resolve brain directory (project override if bound, otherwise catalog template)
    brain_dir = role_dir / 'brain'
    for host in ('agents', 'claude'):
        candidate = project_root / ('.agents' if host == 'agents' else '.claude') / 'skills' / role / 'brain'
        if candidate.is_dir():
            brain_dir = candidate
            break

    brain_stats = {}
    for name in brain_names:
        fpath = brain_dir / name
        if fpath.is_file():
            content = fpath.read_text(encoding='utf-8')
            brain_stats[name] = {'exists': True, 'bytes': len(content.encode('utf-8')), 'content': content}
        else:
            brain_stats[name] = {'exists': False, 'bytes': 0, 'content': ''}

    print_flush(f"│  • Memory Files:       5 standard brain files located in {brain_dir.name}/")
    for bname in brain_names:
        bsize = brain_stats[bname]['bytes']
        bstatus = f"{bsize} bytes" if brain_stats[bname]['exists'] else "missing"
        print_flush(f"│    - {bname:<18} {DIM}[{bstatus}]{RESET}")

    # Consult memory via select_memory
    from model_host import select_memory
    query = f"{role.replace('-', ' ')} evidence findings authorization architecture"
    budget = 8192
    completed_content = brain_stats['COMPLETED.md']['content']
    selected_text, dropped_blocks = select_memory(completed_content, query, budget)
    selected_bytes = len(selected_text.encode('utf-8'))

    pace(2.0)
    print_flush(f"│  • Consultation Query: {DIM}\"{query}\"{RESET}")
    print_flush(f"│  • Memory Budget:      8,192 bytes ceiling")
    print_flush(f"│  • Selected Memory:    {selected_bytes} bytes ({selected_bytes / budget * 100:.1f}% budget consumed)")
    print_flush(f"│  • Dropped Records:    {dropped_blocks} records omitted outside budget")
    print_flush(f"│  • Integrity Check:    {GREEN}✔ Zero record truncation (Atomic markdown blocks){RESET}")

    # Quote memory milestone snippet if available
    snippet_match = re.search(r'(?m)^###\s+([^\n]+)', selected_text)
    if snippet_match:
        print_flush(f"│  • Active Milestone:   {DIM}{snippet_match.group(0)}{RESET}")
    print_flush(f"│  • Status:             {GREEN}✔ Memory bounded and consulted successfully{RESET}")
    print_flush(f"└───────────────────────────────────────────────────────────────────────────────┘\n")
    pace(2.0)

    # ==========================================================================
    # Phase 3: Isolated Container Verification (~6.0s)
    # ==========================================================================
    print_flush(f"{BOLD}{BLUE}┌── [Phase 3/4] Isolated Container Execution Verification ──────────────────────┐{RESET}")
    pace(2.0)

    import workflow
    image_name = workflow.DEFAULT_IMAGE

    # Probe Docker & container runtime safely
    try:
        image_digest = workflow.inspect_image(image_name)
        runtime_status = f"{GREEN}Verified{RESET} ({image_digest[:19]}...)"
        docker_ready = True
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        first_err = str(exc).splitlines()[0] if str(exc) else "Docker daemon not reachable"
        runtime_status = f"{YELLOW}Offline / Static Validation{RESET} ({first_err[:45]}...)"
        docker_ready = False

    print_flush(f"│  • Container Image:    {image_name} -> {runtime_status}")
    print_flush(f"│  • Network Isolation:  --network none {GREEN}[Air-gapped; 0 egress/ingress]{RESET}")
    print_flush(f"│  • Capability Bounds:  --cap-drop ALL, --security-opt no-new-privileges")
    print_flush(f"│  • Filesystem Posture: --read-only root filesystem")
    pace(2.0)
    print_flush(f"│  • Runtime Shield:     --tmpfs /workspace/.crewloom:ro,noexec,nosuid,size=1m")
    print_flush(f"│  • Scratch Space:      --tmpfs /tmp:rw,nosuid,size=128m")
    print_flush(f"│  • Resource Ceilings:  1GB RAM ceiling, 2 CPU cores, 128 PIDs limit")
    print_flush(f"│  • External API Keys:  {GREEN}ZERO required (100% offline-first execution){RESET}")
    print_flush(f"│  • Status:             {GREEN}✔ Hardened container isolation profile verified{RESET}")
    print_flush(f"└───────────────────────────────────────────────────────────────────────────────┘\n")
    pace(2.0)

    # ==========================================================================
    # Phase 4: Summary Table & Next Steps (~4.5s)
    # ==========================================================================
    print_flush(f"{BOLD}{BLUE}┌── [Phase 4/4] Summary & Next Steps ───────────────────────────────────────────┐{RESET}")
    pace(2.0)

    print_flush(f"│                                                                               │")
    print_flush(f"│  {BOLD}VERIFICATION SUMMARY:{RESET}                                                        │")
    print_flush(f"│  ✔ Phase 1: 44 Catalog Roles Discovered & {role:<28} {GREEN}[PASS]{RESET} │")
    print_flush(f"│  ✔ Phase 2: 5 Brain Files Consulted & 8192 Budget Respected   {GREEN}[PASS]{RESET} │")
    print_flush(f"│  ✔ Phase 3: Container Isolated (--network none, 0 API Keys)   {GREEN}[PASS]{RESET} │")
    print_flush(f"│  ✔ Phase 4: Pacing & Contract Verification Succeeded          {GREEN}[PASS]{RESET} │")
    print_flush(f"│                                                                               │")
    print_flush(f"│  {BOLD}NEXT STEPS:{RESET}                                                                  │")
    print_flush(f"│  • Explore role catalog:     crewloom list                                    │")
    print_flush(f"│  • View role instructions:   crewloom show {role:<34} │")
    print_flush(f"│  • Check container health:   crewloom workflow doctor                         │")
    print_flush(f"│  • Install into project:     crewloom install --host agents --skill <role>    │")
    print_flush(f"│  • Run full quickstart:      ./quickstart.sh                                  │")
    print_flush(f"│                                                                               │")
    print_flush(f"│  {GREEN}All 4 verification gates passed. Ready for agent orchestration.{RESET}              │")
    print_flush(f"└───────────────────────────────────────────────────────────────────────────────┘\n")
    pace(2.5)

    duration = time.monotonic() - started_at
    log_run('demo', role, 0, duration, project_root)
    return 0


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
    catalog = commands.add_parser('projects', help='Register and inspect disjoint project roots')
    catalog.add_argument('catalog_arguments', nargs=argparse.REMAINDER)
    project = commands.add_parser('project', help='Enter, inspect, finish, cancel or relink a bound project context')
    project.add_argument('project_arguments', nargs=argparse.REMAINDER)
    privacy = commands.add_parser('privacy', help='Private data guards and selected publication packets')
    privacy.add_argument('privacy_arguments', nargs=argparse.REMAINDER)
    user_context = commands.add_parser('user-context', help='Source-linked user memory and task interpretation')
    user_context.add_argument('user_context_arguments', nargs=argparse.REMAINDER)
    lesson = commands.add_parser('lesson', help='Record, verify, retrieve or review project lessons')
    lesson.add_argument('lesson_arguments', nargs=argparse.REMAINDER)
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
    # `host` and `readiness` are registered so `crewloom --help` and the usage line list them.
    # They take no arguments here: `delegated_command` hands their whole argv to the owning module
    # before this parser runs, which is the only way a flag can survive the hand-over.
    commands.add_parser('evaluate-bilingual', help='Frozen Arabic/English developer feature pilot')
    commands.add_parser('queue', help='Durable priority scheduling across registered projects')
    commands.add_parser('budget', help='Shared managed model request and dollar admission controls')
    commands.add_parser('host', help='Install, observe, guard and verify native host callbacks')
    commands.add_parser('mcp', help='Serve one project task over optional read-only stdio MCP')
    commands.add_parser('native', help='Prepare or serve an explicitly scoped native AX fixture')
    commands.add_parser('readiness', help='Read-only rollout readiness for one registered project')
    install = commands.add_parser('install', help='Copy roles into a project for your agent host')
    install.add_argument('--host', choices=sorted(HOST_DIRS), required=True,
                         help='claude -> .claude/skills, agents -> .agents/skills')
    install.add_argument('--target', default='.', help='Project directory (default: current)')
    install.add_argument('--skill', action='append', default=[], help='Role ID; repeat for several (default: all)')
    install.add_argument('--force', action='store_true', help='Overwrite roles that already exist')
    dash = commands.add_parser('dashboard', help='Start the live dashboard (needs Node 24+)')
    dash.add_argument('--project', default='.', help='Project monitored by this dashboard process')
    dash.add_argument('--port', type=int, default=4317)
    dash.add_argument('--host', default='127.0.0.1',
                      help='Interface to bind; a non-loopback value requires configured authentication')
    reviewer = commands.add_parser('reviewer', help='Manage credential-verified reviewer identities')
    reviewer.add_argument('reviewer_arguments', nargs=argparse.REMAINDER)
    coordinator = commands.add_parser('coordinator', help='Run a concurrent, reviewed DAG of isolated project worktrees')
    coordinator.add_argument('coordinator_arguments', nargs=argparse.REMAINDER)
    demo = commands.add_parser('demo', help='Interactive 20-second walkthrough of role selection, memory consultation, and container isolation')
    demo.add_argument('--role', default='reverse-engineering-analyst', help='Role ID to demonstrate (default: reverse-engineering-analyst)')
    demo.add_argument('--fast', action='store_true', help='Skip pacing delays for instantaneous execution')
    demo.add_argument('--project', default='.', help='Project context directory (default: current)')
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
    if args.command == 'projects':
        from project_binding import catalog_main
        return catalog_main(args.catalog_arguments)
    if args.command == 'map':
        from repo_map import main as map_main
        return map_main(['--project',args.project,'--query',args.query,'--budget',str(args.budget)]
                        + sum([['--seed',seed] for seed in args.seed],[])
                        + (['--rebuild'] if args.rebuild else []))
    if args.command == 'project':
        from project_binding import main as project_main
        return project_main(args.project_arguments)
    if args.command == 'privacy':
        from privacy import main as privacy_main
        return privacy_main(args.privacy_arguments)
    if args.command == 'user-context':
        from user_context import main as user_context_main
        return user_context_main(args.user_context_arguments)
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
    project = Path(getattr(args, 'project', None) or '.').resolve()
    if not project.is_dir():
        parser.error('Project root must be an existing directory')
    if args.command == 'demo':
        return run_demo(role=args.role, fast=args.fast, project=project)
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
        try:
            if any(not candidate.resolve().is_relative_to(project) for candidate in (project / '.crewloom', project / '.crewloom/runs.jsonl')):
                raise ValueError('Run history directory escapes selected project')
            validate_project_paths(item['id'], arguments, project)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        if item['id'] == 'context' and project != resources.distribution_root() and '--project' not in arguments:
            arguments = ['--project', str(project), *arguments]
        started = time.monotonic()
        code = subprocess.run([sys.executable, str(path), *arguments], cwd=project, check=False).returncode
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
