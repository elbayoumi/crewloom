"""Project-bound workflow execution, resumable evidence, and Docker isolation."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1]
ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*$')
MEMORY = ('ARCHITECTURE', 'COMPLETED', 'CHALLENGES', 'IDEAS_VAULT', 'ROADMAP_TODO')
DEFAULT_IMAGE = 'python:3.14-slim'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def safe_path(root, value, internal=False):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('Expected a project-relative path')
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Path escapes selected project: ' + value)
    if internal:
        current = root
        for part in Path(value).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('Runtime state path may not use symlinks')
    if not internal and any(part in ('.crewloom', '.git') for part in (*Path(value).parts, *path.relative_to(root).parts)):
        raise ValueError('Workflow artifacts cannot use runtime or Git state')
    return path


def hashes(root, paths):
    result = {}
    for relative in paths:
        path = safe_path(root, relative)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing or empty artifact: ' + relative)
        result[relative] = digest(path.read_bytes())
    return result


def read_plan(root, filename):
    source = safe_path(root, filename)
    plan = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(plan, dict) or plan.get('schema_version') != 1 or not ID.fullmatch(str(plan.get('id', ''))):
        raise ValueError('Workflow requires schema_version 1 and a stable kebab-case id')
    if plan.get('language', 'en') not in ('en', 'ar'):
        raise ValueError('Language must be en or ar')
    steps = plan.get('steps')
    if not isinstance(steps, list) or not steps:
        raise ValueError('Workflow needs at least one step')
    seen = set()
    outputs = set(); output_targets = set()
    for step in steps:
        if not isinstance(step, dict) or not ID.fullmatch(str(step.get('id', ''))) or step['id'] in seen:
            raise ValueError('Step IDs must be unique kebab-case')
        seen.add(step['id'])
        role = step.get('role')
        if not isinstance(role, str) or not ID.fullmatch(role) or not (LIBRARY / '.agents/skills' / role / 'SKILL.md').is_file():
            raise ValueError('Unknown role')
        kind = step.get('kind', 'command')
        if kind not in ('command', 'task', 'model') or not isinstance(step.get('summary'), str) or not step['summary'].strip():
            raise ValueError('Each step needs a summary and command/task/model kind')
        if kind == 'command':
            argv = step.get('argv')
            if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a or '\0' in a for a in argv):
                raise ValueError('Command argv must be a nonempty string array')
        if kind == 'model':
            from model_host import HOSTS
            if step.get('host') not in HOSTS:
                raise ValueError('Model step needs an explicit codex or claude host')
            if 'model' in step and (not isinstance(step['model'], str) or not step['model'].strip()):
                raise ValueError('Model identifier must be nonempty')
        timeout = step.get('timeout_seconds', 60)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError('Timeout must be an integer from 1 to 3600')
        for field in ('inputs', 'outputs'):
            values = step.get(field)
            if not isinstance(values, list) or (field == 'outputs' and not values):
                raise ValueError('Each step needs inputs and nonempty outputs lists')
            for value in values:
                resolved = safe_path(root, value)
                if field == 'outputs' and (resolved == safe_path(root, filename) or any(resolved == safe_path(root, old) for old in outputs)):
                    raise ValueError('Each artifact needs one owner and cannot overwrite the plan')
                if value in outputs and field == 'outputs':
                    raise ValueError('Each artifact needs one owner')
        for value in step['outputs']:
            target = safe_path(root, value)
            if target in output_targets:
                raise ValueError('Each artifact needs one owner after canonicalization')
            output_targets.add(target)
            if value in outputs or value == filename:
                raise ValueError('Each artifact needs one owner and cannot overwrite the plan')
            outputs.add(value)
    return plan, digest(json.dumps(plan, sort_keys=True).encode())


def runtime(root, ident):
    return safe_path(root, '.crewloom/workflows/' + ident, internal=True)


def save(folder, state):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'state.json'
    if target.is_symlink():
        raise ValueError('State file may not be a symlink')
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(state, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, target)


@contextmanager
def lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'lock'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Workflow locked: another execution or interrupted host owns the lock')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def save_ledger(root, ledger):
    folder = safe_path(root, '.crewloom', internal=True)
    target = safe_path(root, '.crewloom/attempts.json', internal=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, delete=False) as stream:
        temporary = Path(stream.name); json.dump(ledger, stream, ensure_ascii=False)
    os.replace(temporary, target)


def state_for(root, plan, fingerprint):
    folder = runtime(root, plan['id'])
    path = folder / 'state.json'
    if path.exists():
        if path.is_symlink():
            raise ValueError('State file may not be a symlink')
        state = json.loads(path.read_text())
        if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('steps'), dict):
            raise ValueError('Malformed workflow state')
        if state.get('status') not in ('pending', 'running', 'failed', 'complete', 'awaiting_task', 'blocked', 'cancelled'):
            raise ValueError('Malformed workflow progress status')
        definitions = {step['id']: step for step in plan['steps']}
        for ident, record in state['steps'].items():
            if ident not in {step['id'] for step in plan['steps']} or not isinstance(record, dict) or not isinstance(record.get('attempts'), list):
                raise ValueError('Malformed workflow step state')
            if record.get('status') not in ('pending', 'running', 'failed', 'complete') or record.get('role') != definitions[ident]['role']:
                raise ValueError('Malformed workflow ownership or step status')
            if any(not isinstance(attempt, dict) or not isinstance(attempt.get('signature'), str) for attempt in record['attempts']):
                raise ValueError('Malformed workflow attempt history')
            if record.get('status') == 'complete':
                for field in ('inputs', 'outputs'):
                    values = record.get(field)
                    if not isinstance(values, dict) or set(values) != set(definitions[ident][field]) or any(not isinstance(key, str) or not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for key, value in values.items()):
                        raise ValueError('Malformed workflow artifact evidence')
        if state.get('project_root') != str(root) or state.get('plan_sha256') != fingerprint:
            raise ValueError('State belongs to another project or plan revision; use a new workflow ID')
        return folder, state
    return folder, {'schema_version': 1, 'project_root': str(root), 'workflow': plan['id'],
                    'plan_sha256': fingerprint, 'steps': {}, 'status': 'pending'}


def inspect_image(image):
    if not hasattr(os, 'getuid'):
        raise ValueError('Workflow containers require Linux, macOS or WSL; native Windows is not supported yet')
    if not shutil.which('docker'):
        raise ValueError('Docker not installed; isolated execution cannot start')
    result = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image], capture_output=True, text=True, timeout=20)
    if result.returncode or not result.stdout.strip().startswith('sha256:'):
        raise ValueError('Docker/image unavailable; start Docker and explicitly pull ' + image)
    return result.stdout.strip()


def docker_execute(root, argv, image_id, timeout):
    """Only project mounted; runtime state hidden; image immutable; network off."""
    if ',' in str(root):
        raise ValueError('Docker mount paths cannot contain commas')
    name = 'crewloom-' + uuid.uuid4().hex
    command = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '128',
               '--memory', '1g', '--cpus', '2',
               '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:rw,nosuid,size=128m',
               '--tmpfs', '/workspace/.crewloom:ro,noexec,nosuid,size=1m',
               '--mount', f'type=bind,src={root},dst=/workspace',
               '--workdir', '/workspace', '--env', 'HOME=/tmp', '--env', 'PYTHONDONTWRITEBYTECODE=1',
               '--env', 'PYTHONUNBUFFERED=1', image_id, *argv]
    started = time.monotonic()
    captured = bytearray()
    discarded = [False]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    def collect():
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                return
            available = max(0, 65536-len(captured))
            captured.extend(chunk[:available])
            if len(chunk) > available:
                discarded[0] = True
    reader = threading.Thread(target=collect, daemon=True); reader.start()
    try:
        try:
            code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(); code = 124; timed_out = True
    finally:
        subprocess.run(['docker', 'rm', '--force', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if process.poll() is None:
            process.kill(); process.wait()
        reader.join(timeout=5)
        process.stdout.close()
    output = captured.decode('utf-8', errors='replace')
    return {'exit_code': code, 'timed_out': timed_out, 'duration_ms': round((time.monotonic()-started)*1000),
            'output': output, 'output_truncated': discarded[0], 'image_id': image_id, 'network': 'none'}


def verify_completed(root, state):
    for ident, record in state['steps'].items():
        if record.get('status') != 'complete':
            continue
        for field in ('inputs', 'outputs'):
            expected = {key: value for key, value in record[field].items() if field != 'inputs' or key not in record['outputs']}
            if hashes(root, list(expected)) != expected:
                raise ValueError('Stale evidence in ' + ident + '; use a new workflow ID after reviewing changes')


def project_role(root, role):
    candidates = [root / host / 'skills' / role for host in ('.agents', '.claude')]
    installed = [folder for folder in candidates if (folder / 'SKILL.md').is_file()]
    if len(installed) != 1:
        return {'ready': False, 'error': 'Install exactly one project-local copy of the owning role'}
    folder = installed[0]
    for file in [folder / 'SKILL.md', *[folder / 'brain' / (name + '.md') for name in MEMORY]]:
        if not file.resolve().is_relative_to(root) or not file.is_file():
            return {'ready': False, 'error': 'Role memory is missing or escapes the project'}
    return {'ready': True, 'guide': str(folder / 'SKILL.md'), 'memory': str(folder / 'brain')}


def handoff(root, plan, state):
    verify_completed(root, state)
    next_step = next((s for s in plan['steps'] if state['steps'].get(s['id'], {}).get('status') != 'complete'), None)
    return {'project_root': str(root), 'workflow': plan['id'], 'language': plan.get('language', 'en'),
            'status': state['status'], 'next_step': next_step,
            'role_setup': project_role(root, next_step['role']) if next_step else None,
            'completed': {key: {**{field: value[field] for field in ('role', 'summary', 'inputs', 'outputs', 'reviewer') if field in value}, 'attempt_count': len(value['attempts']), 'image_id': value['attempts'][-1].get('image_id') if value['attempts'] else None} for key, value in state['steps'].items() if value.get('status') == 'complete'},
            'next_step_state': ({**{field: state['steps'].get(next_step['id'], {}).get(field) for field in ('status', 'error')}, 'attempt_count': len(state['steps'].get(next_step['id'], {}).get('attempts', []))} if next_step else None),
            'state_file': str(runtime(root, plan['id']) / 'state.json'),
            'blocker': state.get('error'),
            'instruction': 'Read the selected role and project memory; retain this root and verify every supplied artifact.'}


def active_workflow(root):
    path=safe_path(root,'.crewloom/active_workflow.json',internal=True)
    if not path.exists():return None
    value=json.loads(path.read_text())
    if not isinstance(value,dict) or value.get('project_root')!=str(root) or not ID.fullmatch(str(value.get('workflow',''))) or not re.fullmatch('[0-9a-f]{64}',str(value.get('plan_sha256',''))):
        raise ValueError('Invalid or cross-project active workflow reservation')
    return value


def reserve_workflow(root, plan, fingerprint):
    value=active_workflow(root)
    if value and (value['workflow']!=plan['id'] or value['plan_sha256']!=fingerprint):
        raise ValueError('Project already has an unfinished workflow: '+value['workflow']+'; finish or explicitly cancel it first')
    path=safe_path(root,'.crewloom/active_workflow.json',internal=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name)
        json.dump({'project_root':str(root),'workflow':plan['id'],'plan_sha256':fingerprint},stream)
    os.replace(temporary,path)


def cancel(root, plan, fingerprint):
    with lock(safe_path(root,'.crewloom',internal=True)):
        folder,state=state_for(root,plan,fingerprint)
        if not (folder/'state.json').is_file():raise ValueError('Cannot cancel an unstarted workflow')
        value=active_workflow(root)
        if value and (value['workflow']!=plan['id'] or value['plan_sha256']!=fingerprint):
            raise ValueError('Cancel must name the active workflow and unchanged plan')
        if state['status']=='complete':raise ValueError('Completed workflow does not need cancellation')
        state['status']='cancelled';save(folder,state)
        safe_path(root,'.crewloom/active_workflow.json',internal=True).unlink(missing_ok=True)
        return {'project_root':str(root),'workflow':plan['id'],'status':'cancelled',
                'instruction':'Inspect partial artifacts. Cancellation preserves files and failure history; use a new workflow ID for new work.'}


def run(root, plan, fingerprint, image, accept=None, reviewer=None):
    with lock(safe_path(root,'.crewloom',internal=True)):
        _,state=state_for(root,plan,fingerprint)
        if state['status']=='cancelled':raise ValueError('Cancelled workflow cannot resume; use a new workflow ID')
        reserve_workflow(root,plan,fingerprint)
        try:
            return _run_locked(root,plan,fingerprint,image,accept,reviewer)
        finally:
            _,latest=state_for(root,plan,fingerprint)
            if latest['status'] in ('complete','failed','blocked'):
                safe_path(root,'.crewloom/active_workflow.json',internal=True).unlink(missing_ok=True)


def _run_locked(root, plan, fingerprint, image, accept=None, reviewer=None):
    folder, state = state_for(root, plan, fingerprint)
    verify_completed(root, state)
    if accept:
        next_step = next((s for s in plan['steps'] if state['steps'].get(s['id'], {}).get('status') != 'complete'), None)
        if not next_step or next_step['id'] != accept or next_step.get('kind') != 'task':
            raise ValueError('Accept must name the next outstanding task')
    ledger_file = safe_path(root, '.crewloom/attempts.json', internal=True)
    ledger = json.loads(ledger_file.read_text()) if ledger_file.exists() else {'attempts': []}
    if not isinstance(ledger, dict) or not isinstance(ledger.get('attempts'), list) or any(not isinstance(item, dict) or item.get('status') not in ('running', 'failed', 'succeeded') or not isinstance(item.get('signature'), str) for item in ledger['attempts']):
        raise ValueError('Malformed project attempt ledger')
    image_id = None
    for step in plan['steps']:
        record = state['steps'].setdefault(step['id'], {'status': 'pending', 'role': step['role'], 'summary': step['summary'], 'attempts': []})
        if record['status'] == 'complete':
            continue
        try:
            inputs = hashes(root, step['inputs'])
        except ValueError as exc:
            state['status'] = 'blocked'; state['error'] = str(exc); save(folder, state)
            return handoff(root, plan, state)
        state.pop('error', None)
        if step.get('kind') == 'task':
            if accept != step['id']:
                state['status'] = 'awaiting_task'; save(folder, state); return handoff(root, plan, state)
            if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100 or reviewer.strip() == step['role']:
                raise ValueError('Task completion needs a reviewer identifier different from the owning role')
            record.update(status='complete', inputs=inputs, outputs=hashes(root, step['outputs']), reviewer=reviewer)
            state['status'] = 'complete' if step is plan['steps'][-1] else 'pending'
            save(folder, state)
            return handoff(root, plan, state)
        if accept:
            raise ValueError('Accept only the next task step; commands must run to produce evidence')
        if step.get('kind') == 'model':
            run_model_step(root, plan, step, inputs, record, state, folder, ledger)
            if record['status'] != 'complete':
                return handoff(root, plan, state)
            continue
        try:
            image_id = image_id or inspect_image(image)
        except ValueError as exc:
            state['status'] = 'blocked'; state['error'] = str(exc); save(folder, state)
            raise
        signature = digest(json.dumps({'inputs': inputs, 'argv': step['argv'], 'image_id': image_id}, sort_keys=True).encode())
        if sum(a['signature'] == signature and a['status'] != 'succeeded' for a in ledger['attempts']) >= 2:
            state['status'] = 'blocked'; save(folder, state)
            raise ValueError('Two attempts exhausted for unchanged command and inputs')
        before = {rel: (safe_path(root, rel).stat().st_mtime_ns, safe_path(root, rel).stat().st_ino) for rel in step['outputs'] if safe_path(root, rel).is_file()}
        attempt = {'signature': signature, 'status': 'running', 'started_at': time.time()}
        record['attempts'].append(attempt)
        project_attempt = {'signature': signature, 'status': 'running', 'workflow': plan['id'], 'step': step['id']}
        ledger['attempts'].append(project_attempt)
        save_ledger(root, ledger)
        record['status'] = 'running'; state['status'] = 'running'; save(folder, state)
        result = docker_execute(root, step['argv'], image_id, step.get('timeout_seconds', 60))
        attempt.update(result); attempt['status'] = 'finished'
        record['inputs'] = inputs
        try:
            if result['exit_code']:
                raise ValueError('Command failed: ' + step['id'])
            record['outputs'] = hashes(root, step['outputs'])
            for rel, previous in before.items():
                stat = safe_path(root, rel).stat()
                if previous == (stat.st_mtime_ns, stat.st_ino):
                    raise ValueError('Unchanged pre-existing output is not fresh execution evidence: ' + rel)
        except ValueError as exc:
            project_attempt['status'] = 'failed'; save_ledger(root, ledger)
            record['status'] = 'failed'; state['status'] = 'failed'; record['error'] = str(exc)
            save(folder, state); return handoff(root, plan, state)
        project_attempt['status'] = 'succeeded'; save_ledger(root, ledger)
        record['status'] = 'complete'; record.pop('error', None); save(folder, state)
    state['status'] = 'complete'; save(folder, state)
    return handoff(root, plan, state)


def run_model_step(root, plan, step, inputs, record, state, folder, ledger):
    import model_host as host_module
    from model_host import build_prompt, generate
    try:
        prompt=build_prompt(root,step,plan.get('language','en'))
        signature=digest(json.dumps({'prompt':prompt,'host':step['host'],'model':step.get('model'),
                                    'timeout':step.get('timeout_seconds',180),
                                    'adapter_sha256':digest(Path(host_module.__file__).read_bytes())},sort_keys=True).encode())
        if sum(a['signature']==signature and a['status']!='succeeded' for a in ledger['attempts'])>=2:
            raise ValueError('Two attempts exhausted for unchanged model task and inputs')
        attempt={'signature':signature,'status':'running','started_at':time.time()}
        record['attempts'].append(attempt)
        entry={'signature':signature,'status':'running','workflow':plan['id'],'step':step['id']}
        ledger['attempts'].append(entry);save_ledger(root,ledger)
        record['status']='running';state['status']='running';save(folder,state)
        artifacts,evidence=generate(step['host'],prompt,step['outputs'],step.get('timeout_seconds',180),step.get('model'))
        if hashes(root,step['inputs']) != inputs:
            raise ValueError('Inputs changed during model generation; outputs rejected')
        # Preflight every destination before any write. Never follow output aliases.
        destinations={}
        for relative in artifacts:
            current=root
            for part in Path(relative).parts:
                current=current/part
                if current.is_symlink():raise ValueError('Model outputs cannot follow symlinks')
            path=safe_path(root,relative)
            if path.exists() and not path.is_file():raise ValueError('Output must be a file')
            destinations[relative]=path
        for relative,path in destinations.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as stream:
                temporary=Path(stream.name);stream.write(artifacts[relative])
            os.replace(temporary,path)
        attempt.update(evidence,status='finished',exit_code=0)
        entry['status']='succeeded';save_ledger(root,ledger)
        record.update(status='complete',inputs=inputs,outputs=hashes(root,step['outputs']))
        record.pop('error',None);save(folder,state)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        if 'entry' in locals():
            entry['status']='failed';save_ledger(root,ledger)
            attempt.update(status='finished',exit_code=2)
        record['status']='failed';record['error']=str(exc)
        state['status']='failed';state['error']=str(exc);save(folder,state)


def doctor(image, root=None, host=None, model_host=None):
    checks = {'python': os.sys.version.split()[0], 'git': bool(shutil.which('git')), 'docker': bool(shutil.which('docker'))}
    try:
        checks['image_id'] = inspect_image(image); checks['isolated_execution_ready'] = True
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        checks['isolated_execution_ready'] = False; checks['error'] = str(exc)
    if model_host:
        from model_host import probe
        try: checks['model_host'] = probe(model_host)
        except (ValueError, OSError, subprocess.SubprocessError) as exc: checks['model_host'] = {'generation_supported': False, 'error': str(exc)}
    if root and host:
        directory = root / ('.agents' if host == 'agents' else '.claude') / 'skills'
        checks['host_layout'] = host
        checks['installed_roles'] = [p.parent.name for p in directory.glob('*/SKILL.md')]
        checks['host_model_execution_verified'] = False
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'status', 'handoff', 'accept', 'cancel', 'doctor'))
    parser.add_argument('--project', help='Explicit canonical project root; required for task actions')
    parser.add_argument('--plan', default='workflow.json')
    parser.add_argument('--image', default=DEFAULT_IMAGE)
    parser.add_argument('--host', choices=('agents', 'claude'))
    parser.add_argument('--step'); parser.add_argument('--reviewer')
    parser.add_argument('--model-host', choices=('codex', 'claude'))
    args = parser.parse_args(argv)
    if args.action != 'doctor' and not args.project:
        parser.error('Task actions require --project; current working directory is not project identity')
    try:
        if args.action == 'doctor':
            result = doctor(args.image, Path(args.project or '.').resolve(), args.host, args.model_host)
        else:
            root = Path(args.project).resolve(strict=True)
            if not root.is_dir(): raise ValueError('Project must be a directory')
            plan, fingerprint = read_plan(root, args.plan)
            if args.action in ('status', 'handoff'):
                _, state = state_for(root, plan, fingerprint); result = handoff(root, plan, state)
            elif args.action == 'cancel':
                result = cancel(root, plan, fingerprint)
            else:
                if args.action == 'accept' and not args.step: raise ValueError('Accept needs --step')
                result = run(root, plan, fingerprint, args.image, args.step if args.action == 'accept' else None, args.reviewer)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.action in ('status', 'handoff', 'accept', 'cancel') or result.get('status') == 'complete' or result.get('isolated_execution_ready') else 2
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
