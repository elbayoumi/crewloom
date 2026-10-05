#!/usr/bin/env python3
"""Create a fresh ledgerline project that a Crewloom coordinator batch can develop.

One command, one destination, no guessing:

    python3 examples/concurrent-development/setup_project.py \
        --destination /private/tmp/ledgerline --project-id ledgerline-demo \
        --model-host openai --model gpt-4.1

Every refusal happens before the first byte is written: an existing or aliased destination,
a destination inside the Crewloom installation or inside another bound project or Git work
tree, an unknown host, a missing exact model and an unauthorised native CLI host all stop
here. The command never chooses a model, never falls back to another host, and never
contacts a provider; it only proves the requested host is usable.

What it writes, in order: the example assets, the substituted workflows and manifest, the
portable project configuration, the local binding, the two roles the workflows name, one
Git commit of all of it through the configured hooks, a freshly registered reviewer
credential in owner-only runtime state, and finally the coordinator's own read-only
preflight. The last step is the real acceptance of the setup: if the manifest, the DAG, the
identity or the acceptance criteria do not hold, setup says so and leaves the destination
for inspection.
"""
import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import crewloom_resources as resources
except ImportError:  # a source checkout: the flat runtime modules live beside this example
    CHECKOUT = Path(__file__).resolve().parents[2] / 'scripts'
    if not (CHECKOUT / 'crewloom_resources.py').is_file():
        raise SystemExit('Crewloom is not importable here. Install the wheel, or run this '
                         'command from a Crewloom source checkout.')
    sys.path.insert(0, str(CHECKOUT))
    import crewloom_resources as resources

LIBRARY = str(resources.module_file('project_binding.py').parent)
if LIBRARY not in sys.path:
    sys.path.insert(0, LIBRARY)

import crewloom  # noqa: E402
import model_host  # noqa: E402
import project_binding as pb  # noqa: E402
import repo_map  # noqa: E402
import task_coordinator as tc  # noqa: E402
import workflow as w  # noqa: E402

ASSETS = 'examples/concurrent-development/project'
TEMPLATES = ('coordinator.json', 'workflows/billing.json', 'workflows/planning.json',
             'workflows/report.json')
ROLES = ('fullstack-mvp-engineer', 'qa-test-automation-engineer')
DEFAULT_BATCH = 'ledgerline-batch'
DEFAULT_REVIEWER = 'example-reviewer'
EXAMPLE_IDENTITY = ('Crewloom ledgerline example', 'ledgerline@example.invalid')

# Each template value is substituted whole or not at all: a token inside a longer string is a
# mistake in the template, not something to guess around.
TOKENS = {
    '__PROJECT_ID__': 'text', '__BATCH_ID__': 'text', '__MODEL_HOST__': 'text',
    '__MODEL__': 'text', '__NATIVE_HOST_CLI__': 'boolean',
}


class SetupRefusal(Exception):
    """A condition this example refuses, stated before anything was written."""


def git(root, *arguments, check=True):
    return subprocess.run(['git', *arguments], cwd=str(root), env=repo_map.git_environment(),
                          capture_output=True, text=True, timeout=60, check=check)


def canonical_destination(value):
    """The one destination this command will write to, or a refusal.

    The path has to be the canonical one: on macOS `/tmp` is a link to `/private/tmp`, and a
    batch that records a project root the operator cannot name again is a batch whose
    recorded root is wrong.
    """
    if not isinstance(value, str) or not value.strip():
        raise SetupRefusal('--destination needs an explicit path')
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    normalized = Path(os.path.normpath(str(raw)))
    if normalized.name in ('', '.', '..') or str(normalized) == os.sep:
        raise SetupRefusal('Refusing to use a filesystem root as the project destination')
    if os.path.lexists(str(normalized)):
        raise SetupRefusal('The destination already exists; this example only writes a fresh '
                           'directory: ' + str(normalized))
    parent = normalized.parent
    if not parent.is_dir():
        raise SetupRefusal('The destination parent does not exist: ' + str(parent))
    if parent.resolve() != parent:
        raise SetupRefusal('The destination reaches the filesystem through a symlink; pass the '
                           'canonical path instead: ' + str(parent.resolve() / normalized.name))
    if normalized.is_symlink():
        raise SetupRefusal('The destination itself may not be a symlink')
    return normalized


def refuse_unsafe_location(destination):
    """Refuse a destination inside the toolkit, another project, or another Git work tree."""
    trusted = [str(Path(item).resolve()) for item in
               (*resources.installed_roots(), resources.distribution_root())]
    candidate = str(destination)
    for root in trusted:
        if candidate == root or candidate.startswith(root + os.sep):
            raise SetupRefusal('The destination is inside the Crewloom installation at ' + root
                               + '; choose a directory of your own')
    if str(Path(__file__).resolve().parent) in candidate:
        raise SetupRefusal('The destination is inside this example; copy it somewhere else')
    if '.crewloom' in destination.parts:
        raise SetupRefusal('The destination may not sit inside runtime state (.crewloom)')
    for parent in [destination, *destination.parents]:
        if (parent / pb.CONFIG_NAME).is_file() or (parent / pb.BINDING_RELATIVE).is_file():
            raise SetupRefusal('The destination is inside the bound project at ' + str(parent)
                               + '; a coordinator batch needs a project root of its own')
        if (parent / '.agents' / 'skills').is_dir() or (parent / '.claude' / 'skills').is_dir():
            raise SetupRefusal('The destination is inside an installed role tree at ' + str(parent))
    nearest = next((parent for parent in [destination, *destination.parents] if parent.is_dir()),
                   None)
    if nearest is not None:
        inside = git(nearest, 'rev-parse', '--show-toplevel', check=False)
        if inside.returncode == 0 and inside.stdout.strip():
            raise SetupRefusal('The destination is inside the Git work tree at '
                               + inside.stdout.strip()
                               + '; give a directory that is not already version controlled')


def check_model(host, model, native):
    """One exact host and one exact model, with the two native decisions already made."""
    from provider_gateway import PROVIDERS
    if host not in model_host.HOSTS:
        raise SetupRefusal('Unknown model host: ' + host + '; choose one of '
                           + ', '.join(model_host.HOSTS))
    if not isinstance(model, str) or not model.strip() or len(model) > 200 \
            or any(ord(char) < 32 for char in model):
        raise SetupRefusal('--model needs the exact model identifier to request; this example '
                           'never picks one and never falls back to another')
    if host in model_host.CLI_HOSTS and not native:
        raise SetupRefusal(host + ' is reached through an installed CLI, which is the native host '
                           'exception; pass --native-host-cli to record that decision in the '
                           'manifest as well as in the run')
    if host not in model_host.CLI_HOSTS and native:
        raise SetupRefusal(host + ' is a tool-free RPC host and needs no native exception; drop '
                           '--native-host-cli')
    if host in PROVIDERS:
        variable = PROVIDERS[host][1]
        if not os.environ.get(variable):
            raise SetupRefusal('Configure ' + variable + ' in this shell before starting a batch '
                               'on ' + host + '. This example will not substitute another host or '
                               'model when a credential is missing.')
        return {'credential_variable': variable}
    try:
        probe = model_host.probe(host)
    except (ValueError, OSError) as exc:
        raise SetupRefusal('The requested host is not usable here: ' + str(exc)[:200]) from None
    return {'probed_host': probe.get('host'), 'probed_version': probe.get('version')}


def substitute(document, values):
    """Replace sentinel values in a parsed template; anything else is a template error."""
    if isinstance(document, dict):
        return {key: substitute(value, values) for key, value in document.items()}
    if isinstance(document, list):
        return [substitute(item, values) for item in document]
    if isinstance(document, str):
        for token, kind in TOKENS.items():
            if document == token:
                value = values[token]
                if kind == 'boolean':
                    if type(value) is not bool:
                        raise SetupRefusal(token + ' needs a boolean value')
                    return value
                if not isinstance(value, str) or not value.strip():
                    raise SetupRefusal(token + ' needs a nonempty text value')
                return value
        if any(token in document for token in TOKENS):
            raise SetupRefusal('A template token appears inside a larger value: ' + document[:80])
    return document


def copy_assets(destination):
    """Copy the shipped example assets through the installed resource resolver."""
    source = resources.require(ASSETS, 'Concurrent development example')
    shutil.copytree(source, destination, symlinks=False)
    return sorted(str(path.relative_to(destination)) for path in destination.rglob('*')
                  if path.is_file())


def write_configuration(root, project_id):
    """The portable configuration, then the local binding. No entered-task reservation.

    `pb.bootstrap` is the documented first footprint: it writes the binding and the local
    ignore rule without reserving the root for a task that nobody is running, so a
    coordinator batch is not refused by a reservation this setup created.
    """
    config = pb.default_config(project_id, 'observe')
    config['policy'] = {**config['policy'],
                        'review': {'mode': 'verified', 'allow_self_review': False}}
    config['exclude'] = sorted(set(config['exclude']) | {'artifacts'})
    pb.write_json(root, pb.CONFIG_NAME, config)
    report = pb.bootstrap(root, project_id=project_id)
    return {'config_path': report['config_path'], 'created': report['created'],
            'checkout_id': report['binding']['checkout_id'],
            'review_policy': {'mode': 'verified', 'allow_self_review': False}}


def install_roles(root):
    """Only the roles the four workflows actually name."""
    installed, errors = crewloom.install_skills(root, 'agents', list(ROLES), False)
    if errors:
        raise SetupRefusal('Role installation failed: ' + ', '.join(errors))
    return installed


def run_helper_tests(root):
    """The frozen fixture tests for the reused helpers, before any batch exists."""
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                             '-p', 'test_*.py'], cwd=str(root), capture_output=True, text=True,
                            timeout=180)
    if result.returncode:
        raise SetupRefusal('The frozen helper tests failed in the new project; nothing was '
                           'committed: ' + (result.stderr.strip()[-300:] or 'see the output'))
    return {'ran': 'discovered tests/', 'returncode': result.returncode}


def commit_base(root):
    """One commit of the whole portable project, through whatever hooks are configured."""
    git(root, 'init', '-q')
    signing = git(root, 'config', '--get', 'commit.gpgsign', check=False)
    if signing.returncode == 0 and signing.stdout.strip() == 'true':
        raise SetupRefusal('This Git configuration signs every commit; the example does not '
                           'disable signing for you. Configure signing for this repository or '
                           'turn it off deliberately.')
    identity = {}
    for field, value in (('user.name', EXAMPLE_IDENTITY[0]), ('user.email', EXAMPLE_IDENTITY[1])):
        current = git(root, 'config', '--get', field, check=False)
        if current.returncode or not current.stdout.strip():
            git(root, 'config', field, value)
            identity[field] = value
    git(root, 'add', '-A')
    staged = git(root, 'diff', '--cached', '--name-only').stdout.split()
    if not staged:
        raise SetupRefusal('Nothing was staged; the example project would be empty')
    git(root, 'commit', '-m', 'Freeze the ledgerline example project before its first batch')
    return {'commit': git(root, 'rev-parse', 'HEAD').stdout.strip(),
            'staged_count': len(staged), 'identity_configured_here': identity}


def register_reviewer(root, principal):
    """A fresh reviewer principal and its owner-only credential file, never in Git."""
    saved = sys.argv
    sys.argv = ['crewloom', 'reviewer', 'register', '--project', str(root),
                '--principal', principal]
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            code = crewloom.main()
    finally:
        sys.argv = saved
    if code:
        raise SetupRefusal('Reviewer registration failed: ' + captured.getvalue().strip()[-300:])
    report = json.loads(captured.getvalue())
    token = Path(report['token_file'])
    if token.stat().st_mode & 0o077:
        raise SetupRefusal('The issued credential file is not owner-only')
    return {'principal': report['principal'], 'method': report['method'],
            'token_file': report['token_file'],
            'delivery': 'Read the token from that file into CREWLOOM_REVIEWER_TOKEN or standard '
                        'input; it is never a command argument and never tracked in Git.'}


def preflight(root, project_id):
    """The coordinator's own read-only acceptance of what was just written."""
    report = tc.validate(root, 'coordinator.json', project_id)
    return {'status': report['status'], 'base_commit': report['base_commit'],
            'manifest_sha256': report['manifest_sha256'], 'workers': report['workers'],
            'order': report['order'], 'tasks': report['tasks'],
            'integration_workflow': report['integration_workflow'],
            'integration_inputs': report['required_integration_inputs'],
            'model_steps': report['model_steps'], 'native_cli_tasks': report['native_cli_tasks'],
            'native_cli_opt_in': report['native_cli_opt_in'],
            'project_id': report['project_id'], 'checkout_id': report['checkout_id']}


def run(arguments):
    destination = canonical_destination(arguments.destination)
    refuse_unsafe_location(destination)
    if not pb.PROJECT_ID.match(arguments.project_id or ''):
        raise SetupRefusal('--project-id must be a lowercase portable identity of 3 to 64 '
                           'characters')
    if not w.ID.fullmatch(arguments.batch_id or ''):
        raise SetupRefusal('--batch-id must be kebab-case')
    availability = check_model(arguments.model_host, arguments.model, arguments.native_host_cli)
    native = arguments.model_host in model_host.CLI_HOSTS
    values = {'__PROJECT_ID__': arguments.project_id, '__BATCH_ID__': arguments.batch_id,
              '__MODEL_HOST__': arguments.model_host, '__MODEL__': arguments.model.strip(),
              '__NATIVE_HOST_CLI__': native}
    # Every template is read and substituted before the destination exists, so a template or
    # argument error cannot leave a half-configured project behind.
    documents = {}
    for relative in TEMPLATES:
        source = resources.require(ASSETS + '/' + relative, 'Example template ' + relative)
        documents[relative] = substitute(json.loads(source.read_text(encoding='utf-8')), values)
    copied = copy_assets(destination)
    for relative, document in documents.items():
        (destination / relative).write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    configuration = write_configuration(destination, arguments.project_id)
    roles = install_roles(destination)
    helpers = run_helper_tests(destination)
    base = commit_base(destination)
    reviewer = register_reviewer(destination, arguments.reviewer)
    accepted = preflight(destination, arguments.project_id)
    return {'status': 'ready', 'project_root': str(destination),
            'project_id': arguments.project_id, 'batch': arguments.batch_id,
            'model': {'host': arguments.model_host, 'requested': values['__MODEL__'],
                      'native_host_cli': native, 'native_cli_manifest_opt_in': native,
                      'run_flag_required': native, **availability},
            'roles': roles, 'files_copied': len(copied), 'configuration': configuration,
            'helper_tests': helpers, 'base': base, 'reviewer': reviewer, 'preflight': accepted,
            'next_commands': [
                'crewloom coordinator validate --project ' + str(destination)
                + ' --project-id ' + arguments.project_id + ' --manifest coordinator.json',
                'crewloom coordinator run --project ' + str(destination) + ' --project-id '
                + arguments.project_id + ' --manifest coordinator.json'
                + (' --allow-host-cli' if native else ''),
                'crewloom coordinator status --project ' + str(destination) + ' --project-id '
                + arguments.project_id + ' --manifest coordinator.json',
            ],
            'claims': [
                'No provider call was made: the RPC check is an environment lookup and the CLI '
                'check is a bounded version probe.',
                'The requested model is recorded exactly; nothing chooses a substitute and no '
                'unavailable host is silently replaced.',
                'Setup performs no review and approves no generated output; publication needs a '
                'separate reviewed decision.',
                'Credentials and runtime state stay in owner-only .crewloom files that Git '
                'ignores.',
                'Git hooks configured for the repository run; nothing is committed with '
                '--no-verify and no hook is disabled.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--destination', required=True, help='Fresh canonical project directory')
    parser.add_argument('--project-id', required=True, help='Explicit portable project identity')
    parser.add_argument('--model-host', required=True, choices=sorted(model_host.HOSTS),
                        help='The exact host to generate with')
    parser.add_argument('--model', required=True, help='The exact model identifier to request')
    parser.add_argument('--batch-id', default=DEFAULT_BATCH, help='Coordinator batch id')
    parser.add_argument('--reviewer', default=DEFAULT_REVIEWER, help='Fresh reviewer principal')
    parser.add_argument('--native-host-cli', action='store_true',
                        help='Record the installed-CLI native exception in the manifest')
    arguments = parser.parse_args(argv)
    try:
        report = run(arguments)
    except (SetupRefusal, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)[:400]}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())