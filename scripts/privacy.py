"""Project-local private data, staged-index checks and explicit publication packets."""
import argparse
import fnmatch
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile

import project_binding as pb
import repo_map
import workflow as w

POLICY = '.crewloom/private/git-policy.json'
SOURCES = '.crewloom/private/source-paths.json'
MAX_FILE = 2 * 1024 * 1024
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,}|AKIA[0-9A-Z]{16})')


def git(root, *args, input_data=None):
    environment = repo_map.git_environment()
    if args and args[0] in ('ls-files', 'show', 'cat-file') and os.environ.get('GIT_INDEX_FILE'):
        gitdir = Path(git(root, 'rev-parse', '--absolute-git-dir').decode().strip()).resolve()
        index = Path(os.environ['GIT_INDEX_FILE'])
        index = (root / index).resolve() if not index.is_absolute() else index.resolve()
        if not index.is_relative_to(gitdir):
            raise ValueError('Commit index does not belong to the selected checkout')
        environment['GIT_INDEX_FILE'] = str(index)
    result = subprocess.run(['git', *args], cwd=root, env=environment,
                            capture_output=True, check=True, input=input_data)
    return result.stdout


def private_write(root, relative, data):
    import host_lifecycle as hl
    return hl._write_private(w.safe_path(root, relative, internal=True), data, limit=MAX_FILE)


def read_private(root, relative, default):
    path = w.safe_path(root, relative, internal=True)
    if not path.exists():
        return default
    if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > MAX_FILE:
        raise ValueError('Private metadata must be bounded and single-link')
    return json.loads(path.read_text())


def ignores(root, host=None):
    path = pb.writable(root, '.gitignore')
    original = path.read_text() if path.exists() else ''
    lines = ['/.crewloom/', '/.crewloom-repairs/']
    if host:
        lines.append('/' + str(host) + '/*/brain/')
    positions = {line: index for index, line in enumerate(original.splitlines())}
    last_exception = max((index for index, line in enumerate(original.splitlines()) if line.startswith('!')), default=-1)
    missing = [line for line in lines if positions.get(line, -1) <= last_exception]
    if missing:
        candidate = (original.rstrip('\n') + '\n' if original.strip() else '') + '\n'.join(missing) + '\n'
        with tempfile.NamedTemporaryFile(mode='w', dir=root, delete=False) as stream:
            stream.write(candidate)
            temporary = Path(stream.name)
        temporary.replace(path)
    return missing


def source_snapshot(root, relative, data, task_id=None):
    """Copy a user excerpt privately; retain its original name for publication rejection."""
    if SECRET.search(data):
        raise ValueError('Recognized credential in conversation source; remove it before recording')
    destination = '.crewloom/private/inputs/' + w.digest(data) + '.txt'
    private_write(root, destination, data)
    relative = (root / relative).resolve().relative_to(root).as_posix()
    origins = read_private(root, SOURCES, [])
    if relative not in origins and not relative.startswith('.crewloom/private/'):
        origins.append(relative)
        private_write(root, SOURCES, json.dumps(origins).encode())
    ignores(root)
    init(root, task_id=task_id)
    return destination


def private_name(name, origins=(), role_memory=True):
    parts = name.casefold().split('/')
    if role_memory and parts[0] == 'brain':
        return True
    if any(part in ('.crewloom', '.crewloom-repairs', '.git') for part in parts):
        return True
    base = parts[-1]
    if base == '.env' or base.startswith('.env.') and base not in ('.env.example', '.env.sample', '.env.template'):
        return True
    if base.endswith(('.pem', '.key', '.p12', '.pfx')) or base in ('id_rsa', 'id_ed25519'):
        return True
    if name.casefold() in {str(item).casefold() for item in origins}:
        return True
    return role_memory and any(fnmatch.fnmatch(name.casefold(), prefix + '/skills/*/brain/*')
               for prefix in ('.agents', '.claude', '.opencode'))


def check(root, names=None, role_memory=True, extra_origins=()):
    """Read the actual index blobs, including forced additions and already tracked private paths."""
    origins = [*read_private(root, SOURCES, []), *extra_origins]
    indexed = git(root, 'ls-files', '--stage', '-z').decode().split('\0')
    if len(indexed) > 10001:
        raise ValueError('Privacy index exceeds 10000 records; explicit review required')
    entries = []
    findings = []
    for line in indexed:
        if not line:
            continue
        metadata, name = line.split('\t', 1)
        mode, sha, stage = metadata.split()
        if names is not None and name not in names:
            continue
        if stage != '0':
            raise ValueError('Resolve index conflicts before privacy checks')
        if private_name(name, origins, role_memory):
            findings.append({'path': name, 'reason': 'private path is tracked or staged'})
        elif mode != '160000':
            entries.append((name, sha))
    hashes = sorted({sha for _, sha in entries})
    if not hashes:
        return findings
    request = ('\n'.join(hashes) + '\n').encode()
    sizes = {}
    for line in git(root, 'cat-file', '--batch-check', input_data=request).decode().splitlines():
        sha, kind, size = line.split()
        if kind != 'blob':
            raise ValueError('Index entries must reference blob objects')
        sizes[sha] = int(size)
    allowed = [sha for sha in hashes if sizes[sha] <= MAX_FILE]
    if sum(sizes[sha] for sha in allowed) > 64 * 1024 * 1024:
        raise ValueError('Privacy scan exceeds 64 MiB; explicit review required')
    secret_hashes = set()
    if allowed:
        packet = git(root, 'cat-file', '--batch', input_data=('\n'.join(allowed) + '\n').encode())
        offset = 0
        for sha in allowed:
            end = packet.index(b'\n', offset)
            header = packet[offset:end].decode().split()
            if header != [sha, 'blob', str(sizes[sha])]:
                raise ValueError('Malformed index object scan')
            offset = end + 1
            data = packet[offset:offset + sizes[sha]]
            if len(data) != sizes[sha]:
                raise ValueError('Incomplete index object scan')
            if SECRET.search(data):
                secret_hashes.add(sha)
            offset += sizes[sha] + 1
    for name, sha in entries:
        if sizes[sha] > MAX_FILE:
            findings.append({'path': name, 'reason': 'index blob exceeds scan limit; explicit review required'})
        elif sha in secret_hashes:
            findings.append({'path': name, 'reason': 'recognized credential in index blob'})

    return findings


def init(root, task_id=None):
    pb.load_binding(root)
    if Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != root:
        raise ValueError('Privacy setup requires the bound repository root')
    with w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True):
        pb.preflight_ownership(root, task_id)
        if task_id is None and (pb.reservation(root) or w.active_workflow(root)):
            raise ValueError('Finish or cancel the active task before privacy setup')
        import host_lifecycle
        for name in ('inputs', 'overrides', 'exports'):
            host_lifecycle._private_folder(w.safe_path(root, '.crewloom/private/' + name, internal=True))
        # Register older recorded sources too; migration does not expose their text.
        import user_context
        old_store = user_context.load(root)
        origins = read_private(root, SOURCES, [])
        old_items = list(old_store['records']) + list(old_store['contracts'].values())
        for item in list(old_store['contracts'].values()):
            old_items.extend(item.get('history', []))
        for item in old_items:
            relative = item.get('source', {}).get('path')
            if relative and not relative.startswith('.crewloom/private/'):
                canonical = w.safe_path(root, relative).relative_to(root).as_posix()
                if canonical not in origins:
                    origins.append(canonical)
        if origins:
            private_write(root, SOURCES, json.dumps(origins).encode())
        ignores(root)
        if pb.load_binding(root)['project_id'] != 'crewloom-toolkit':
            ignore = pb.writable(root, '.gitignore')
            original = ignore.read_text()
            if '/Brain/' not in original.splitlines():
                ignore.write_text(original.rstrip('\n') + '\n/Brain/\n')
            for host in ('.agents', '.claude', '.opencode'):
                if (root / host / 'skills').is_dir():
                    ignores(root, Path(host) / 'skills')
        hooks = w.safe_path(root, '.crewloom/private/hooks', internal=True)
        configured = subprocess.run(['git', 'config', '--get', 'core.hooksPath'], cwd=root,
                                    env=repo_map.git_environment(), capture_output=True, text=True).stdout.strip()
        existing = read_private(root, POLICY, None)
        configured_path = Path(configured)
        if configured_path.is_absolute() and configured_path.parts[-3:] == ('.crewloom', 'private', 'hooks') and configured != str(hooks):
            owner = configured_path.parent.parent.parent.resolve()
            owner_binding = pb.load_binding(owner)
            owner_policy = read_private(owner, POLICY, None)
            wrapper = w.safe_path(owner, '.crewloom/private/hooks/pre-commit', internal=True)
            common = lambda selected: Path(git(selected, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip()).resolve()
            if owner_binding['project_id'] != pb.load_binding(root)['project_id'] or common(owner) != common(root):
                raise ValueError('Inherited privacy hook belongs to another project')
            if not owner_policy or owner_policy.get('scope') != owner_binding or not wrapper.is_file() or wrapper.is_symlink() or not os.access(wrapper, os.X_OK) or w.digest(wrapper.read_bytes()) != owner_policy.get('wrapper_sha256'):
                raise ValueError('Inherited privacy hook ownership is unknown or changed')
            # Shared core.hooksPath already guards this linked worktree. Replacing it
            # with another wrapper could chain the two owned guards into a cycle.
            return {'status': 'inherited-enabled', 'existing_hooks_preserved': True,
                    'findings': check(root, role_memory=owner_policy.get('private_role_memory', True),
                                      extra_origins=read_private(owner, SOURCES, []))}
        if configured == str(hooks):
            if not existing or existing.get('scope') != pb.load_binding(root):
                raise ValueError('Privacy hook ownership is unknown')
            wrapper = hooks / 'pre-commit'
            if not wrapper.is_file() or wrapper.is_symlink() or w.digest(wrapper.read_bytes()) != existing.get('wrapper_sha256') or not os.access(wrapper, os.X_OK):
                raise ValueError('Privacy hook is missing or changed; restore it before committing')
            return {'status': 'already-enabled', 'findings': check(root, role_memory=existing.get('private_role_memory', True))}
        previous = (root / configured).resolve() if configured else Path(git(root, 'rev-parse', '--git-path', 'hooks').decode().strip())
        if not previous.is_absolute():
            previous = root / previous
        hook = previous / 'pre-commit'
        if hook.exists() and not os.access(hook, os.X_OK):
            raise ValueError('Existing pre-commit is not executable; resolve it without bypassing checks')
        policy = {'scope': pb.load_binding(root), 'previous_hooks': str(previous),
                  'previous_pre_commit': str(hook) if hook.is_file() else None,
                  'private_role_memory': pb.load_binding(root)['project_id'] != 'crewloom-toolkit'}
        private_write(root, POLICY, json.dumps(policy).encode())
        ignores(root)
        hooks.mkdir(parents=True, exist_ok=True)
        # Chain every existing hook, not just pre-commit; no existing hook file is overwritten.
        for source in previous.iterdir() if previous.is_dir() else []:
            if source.is_file() and not source.name.endswith('.sample') and source.name != 'pre-commit':
                target = hooks / source.name
                if target.exists():
                    raise ValueError('Privacy hook destination already exists')
                target.symlink_to(source.resolve())
        wrapper = '#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(Path(__file__).resolve())) + ' hook --project ' + shlex.quote(str(root)) + '\n'
        private_write(root, '.crewloom/private/hooks/pre-commit', wrapper)
        os.chmod(hooks / 'pre-commit', 0o700)
        policy['wrapper_sha256'] = w.digest(wrapper.encode())
        private_write(root, POLICY, json.dumps(policy).encode())
        git(root, 'config', 'core.hooksPath', str(hooks))
        return {'status': 'enabled', 'findings': check(root, role_memory=policy['private_role_memory']), 'existing_hooks_preserved': True}


def relocation_plan(root, binding):
    """Validate an owned guard before rebind changes project metadata."""
    policy = read_private(root, POLICY, None)
    if policy is None:
        return None
    if binding is None or policy.get('scope') != binding:
        raise ValueError('Privacy relocation ownership is unknown')
    old_root = Path(binding['project_root'])
    configured = git(root, 'config', '--get', 'core.hooksPath').decode().strip()
    if configured != str(old_root / '.crewloom/private/hooks'):
        raise ValueError('Privacy hook configuration changed; restore it before rebinding')
    wrapper = w.safe_path(root, '.crewloom/private/hooks/pre-commit', internal=True)
    if not wrapper.is_file() or wrapper.is_symlink() or w.digest(wrapper.read_bytes()) != policy.get('wrapper_sha256'):
        raise ValueError('Privacy hook changed; restore it before rebinding')
    def remap(name):
        path = Path(name)
        return str(root / path.relative_to(old_root)) if path.is_relative_to(old_root) else str(path)
    policy['previous_hooks'] = remap(policy['previous_hooks'])
    if policy.get('previous_pre_commit'):
        policy['previous_pre_commit'] = remap(policy['previous_pre_commit'])
        previous = Path(policy['previous_pre_commit'])
        if not previous.is_file() or not os.access(previous, os.X_OK):
            raise ValueError('Previous pre-commit is unavailable after relocation')
    links = []
    for path in wrapper.parent.iterdir():
        if path.name != 'pre-commit' and path.is_symlink():
            links.append((path, remap(os.readlink(path))))
    return {'policy': policy, 'links': links}


def relocate_guard(root, binding, plan):
    """Re-home owned hooks while preserving existing hook sources."""
    policy = plan['policy']
    wrapper = '#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(Path(__file__).resolve())) + ' hook --project ' + shlex.quote(str(root)) + '\n'
    private_write(root, '.crewloom/private/hooks/pre-commit', wrapper)
    os.chmod(root / '.crewloom/private/hooks/pre-commit', 0o700)
    for path, target in plan['links']:
        path.unlink()
        path.symlink_to(target)
    policy.update(scope=binding, wrapper_sha256=w.digest(wrapper.encode()))
    private_write(root, POLICY, json.dumps(policy).encode())
    git(root, 'config', 'core.hooksPath', str(root / '.crewloom/private/hooks'))


def hook(root):
    policy = read_private(root, POLICY, None)
    if not policy or policy.get('scope') != pb.load_binding(root):
        raise ValueError('Privacy hook project binding changed')
    selected = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    extra_origins = ()
    if selected != root:
        owner_common = Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip()).resolve()
        selected_common = Path(git(selected, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip()).resolve()
        if selected_common != owner_common or pb.load_binding(selected)['project_id'] != policy['scope']['project_id']:
            raise ValueError('Inherited privacy hook belongs to another project')
        extra_origins = read_private(root, SOURCES, [])
    findings = check(selected, role_memory=policy.get('private_role_memory', True), extra_origins=extra_origins)
    if findings:
        return {'status': 'rejected', 'findings': findings}, 2
    previous = policy.get('previous_pre_commit')
    if previous:
        if not Path(previous).is_file() or not os.access(previous, os.X_OK):
            raise ValueError('Previous pre-commit disappeared or is not executable')
        result = subprocess.run([previous], cwd=selected, env=os.environ.copy(), check=False)
        if result.returncode:
            return {'status': 'previous-hook-rejected'}, result.returncode
    return {'status': 'accepted'}, 0


def export(root, names, out):
    pb.load_binding(root)
    if not names or len(set(names)) != len(names) or len(names) > 256:
        raise ValueError('Export requires 1..256 explicit unique --include files')
    origins = read_private(root, SOURCES, [])
    contents = {}
    for name in names:
        if private_name(name, origins):
            raise ValueError('Private file cannot be exported: ' + name)
        path = w.safe_path(root, name)
        w.safe_path(root, name, internal=True)
        if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > MAX_FILE:
            raise ValueError('Export needs bounded regular files without links')
        canonical = path.relative_to(root).as_posix()
        if private_name(canonical, origins) or canonical in contents:
            raise ValueError('Aliased or private export path')
        data = path.read_bytes()
        if SECRET.search(data):
            raise ValueError('Recognized credential in export file: ' + name)
        if sum(len(item) for item in contents.values()) + len(data) > 16 * 1024 * 1024:
            raise ValueError('Export packet exceeds 16 MiB; narrow selected files')
        contents[canonical] = data
    target = w.safe_path(root, out, internal=True)
    if not out.startswith('.crewloom/private/exports/') or not out.endswith('.zip') or target.relative_to(root).as_posix() != out:
        raise ValueError('Publication packet belongs under .crewloom/private/exports/*.zip')
    if target.exists():
        raise ValueError('Export destination already exists')
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in contents.items():
                archive.writestr(name, data)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'packet': out, 'files': sorted(contents), 'sha256': w.digest(target.read_bytes()),
            'published': False, 'limitations': 'Known credential patterns only; review selected content before publishing'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'check', 'hook', 'export'))
    parser.add_argument('--project', required=True)
    parser.add_argument('--include', action='append', default=[])
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    try:
        root = Path(args.project).resolve(strict=True)
        pb.load_binding(root)
        if args.action == 'init':
            result = init(root)
            code = 2 if result.get('findings') else 0
        elif args.action == 'hook':
            result, code = hook(root)
        elif args.action == 'export':
            result, code = export(root, args.include, args.out), 0
        else:
            findings = check(root, role_memory=pb.load_binding(root)['project_id'] != 'crewloom-toolkit')
            result, code = {'findings': findings}, 2 if findings else 0
        print(json.dumps(result, ensure_ascii=False))
        return code
    except (ValueError, OSError, subprocess.SubprocessError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
