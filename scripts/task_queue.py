"""Durable explicit-catalog priority queue. Runs coordinator batches, never publishes them."""
import argparse
import concurrent.futures
import json
import time
import uuid
from pathlib import Path

import project_binding as pb
import task_coordinator as coordinator
import usage_budget as control


def _state(folder):
    state = control.read(folder / 'queue.json')
    if state is None:
        return {'schema_version': 1, 'jobs': []}
    if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('jobs'), list) or len(state['jobs']) > 1000:
        raise ValueError('Malformed or exhausted queue')
    seen = set()
    for job in state['jobs']:
        if not isinstance(job, dict) or not isinstance(job.get('id'), str) or job['id'] in seen or job.get('status') not in ('queued', 'running', 'verified', 'failed', 'cancelled', 'interrupted'):
            raise ValueError('Malformed queue job')
        seen.add(job['id'])
        if type(job.get('priority')) is not int or not -100 <= job['priority'] <= 100:
            raise ValueError('Malformed queue priority')
    return state


def _project(catalog, project_id):
    item = next((p for p in pb.read_catalog(catalog)['projects'] if p['project_id'] == project_id), None)
    if item is None:
        raise ValueError('Project ID is not registered in selected catalog')
    return pb._catalog_binding(item)


def enqueue(directory, catalog, project_id, manifest, priority=0):
    if type(priority) is not int or not -100 <= priority <= 100:
        raise ValueError('Priority must be an integer from -100 to 100')
    root = _project(catalog, project_id)
    binding = pb.load_binding(root)
    meta = coordinator.load_plan(root, manifest, project_id, checks=('structure', 'git', 'clean'))
    folder = control.private_directory(directory)
    with control.locked(folder):
        state = _state(folder)
        if len(state['jobs']) >= 1000:
            raise ValueError('Queue history exhausted; select a new explicit queue period')
        if any(j['project_id'] == project_id and j['manifest'] == manifest and j['status'] in ('queued', 'running', 'interrupted') for j in state['jobs']):
            raise ValueError('This project manifest already has an unfinished queue job')
        job = {'id': uuid.uuid4().hex, 'project_id': project_id, 'checkout_id': binding['checkout_id'],
               'project_root': str(root), 'catalog': str(Path(catalog).resolve(strict=True)),
               'manifest': manifest, 'manifest_sha256': meta['manifest_sha256'], 'plan_fingerprint': meta['fingerprint'],
               'workflow_hashes': {k: v['plan_sha256'] for k, v in meta['workflows'].items()},
               'priority': priority, 'status': 'queued', 'created_at': time.time()}
        state['jobs'].append(job)
        control.write(folder / 'queue.json', state)
        return job


def status(directory):
    folder = control.private_directory(directory, create=False)
    with control.locked(folder):
        return _state(folder)


def change(directory, job_id, action):
    folder = control.private_directory(directory, create=False)
    with control.locked(folder):
        state = _state(folder)
        job = next((j for j in state['jobs'] if j['id'] == job_id), None)
        if job is None:
            raise ValueError('Unknown queue job')
        if action == 'cancel' and job['status'] == 'queued':
            job['status'] = 'cancelled'
        elif action == 'retry' and job['status'] in ('failed', 'interrupted'):
            job.update(status='queued', error=None)
        else:
            raise ValueError('Only queued jobs can be cancelled; only failed/interrupted jobs can be retried. Cancel active batches with coordinator cancel.')
        control.write(folder / 'queue.json', state)
        return job


def _run(job, image, allow_host_cli):
    root = _project(job['catalog'], job['project_id'])
    if str(root) != job['project_root'] or pb.load_binding(root)['checkout_id'] != job['checkout_id']:
        raise ValueError('Queued project root or checkout identity changed')
    meta = coordinator.load_plan(root, job['manifest'], job['project_id'])
    if meta['manifest_sha256'] != job['manifest_sha256'] or meta['fingerprint'] != job['plan_fingerprint'] or {k: v['plan_sha256'] for k, v in meta['workflows'].items()} != job['workflow_hashes']:
        raise ValueError('Queued manifest changed; cancel and enqueue the reviewed manifest again')
    return coordinator.run(root, job['manifest'], job['project_id'], image=image, allow_host_cli=allow_host_cli)


def drain(directory, workers=2, image=coordinator.DEFAULT_IMAGE, allow_host_cli=False):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('Queue workers must be an integer from 1 to 4')
    folder = control.private_directory(directory)
    # One dispatcher per queue; state locks remain short so status/cancel still work.
    with control.locked(folder, 'dispatcher.lock', blocking=False):
        with control.locked(folder):
            state = _state(folder)
            for job in state['jobs']:
                if job['status'] == 'running':
                    job.update(status='interrupted', error='Prior dispatcher exited; inspect batch before explicit retry')
            control.write(folder / 'queue.json', state)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            active = {}
            while True:
                with control.locked(folder):
                    state = _state(folder)
                    roots = {job['project_root'] for job in active.values()}
                    eligible = sorted((j for j in state['jobs'] if j['status'] == 'queued'),
                                      key=lambda j: (-j['priority'], j['created_at']))
                    for job in eligible:
                        if len(active) >= workers:
                            break
                        if job['project_root'] in roots:
                            continue
                        try:
                            root = _project(job['catalog'], job['project_id'])
                            plan = coordinator.load_plan(root, job['manifest'], job['project_id'], checks=('structure',))
                            holder = coordinator._ownership(root, plan['plan']['id'])['holder']
                        except (ValueError, OSError, coordinator.CoordinatorError) as exc:
                            job.update(status='failed', error=str(exc), ended_at=time.time())
                            control.write(folder / 'queue.json', state)
                            continue
                        if holder:
                            job['waiting_for'] = holder
                            control.write(folder / 'queue.json', state)
                            continue
                        job.pop('waiting_for', None)
                        job.update(status='running', started_at=time.time())
                        roots.add(job['project_root'])
                        # Persist intent before any worker can make a provider call.
                        control.write(folder / 'queue.json', state)
                        active[pool.submit(_run, dict(job), image, allow_host_cli)] = dict(job)
                if not active:
                    break
                done, _ = concurrent.futures.wait(active, timeout=0.2,
                                                  return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    job = active.pop(future)
                    try:
                        result = future.result()
                        outcome = {'status': 'verified' if result.get('status') == 'verified' else 'failed',
                                   'batch_status': result.get('status'), 'error': result.get('error')}
                    except Exception as exc:
                        outcome = {'status': 'failed', 'error': str(exc)}
                    with control.locked(folder):
                        state = _state(folder)
                        record = next(j for j in state['jobs'] if j['id'] == job['id'])
                        record.update(outcome, ended_at=time.time())
                        control.write(folder / 'queue.json', state)
    return status(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('enqueue', 'run', 'status', 'cancel', 'retry'))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--catalog'); parser.add_argument('--project-id'); parser.add_argument('--manifest')
    parser.add_argument('--priority', type=int, default=0); parser.add_argument('--job-id')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--image', default=coordinator.DEFAULT_IMAGE)
    parser.add_argument('--allow-host-cli', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'enqueue':
            if not all((args.catalog, args.project_id, args.manifest)):
                parser.error('enqueue needs --catalog, --project-id and --manifest')
            result = enqueue(args.directory, args.catalog, args.project_id, args.manifest, args.priority)
        elif args.action == 'run':
            result = drain(args.directory, args.workers, args.image, args.allow_host_cli)
        elif args.action == 'status':
            result = status(args.directory)
        else:
            result = change(args.directory, args.job_id, args.action)
        print(json.dumps(result, ensure_ascii=False)); return 0
    except (ValueError, OSError, KeyError, TypeError, coordinator.CoordinatorError) as exc:
        print(json.dumps({'error': str(exc)})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
