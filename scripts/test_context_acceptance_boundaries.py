"""Independent regressions from reproduced context and process-ownership failures."""
import hashlib
import json
import multiprocessing
import os
import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import crewloom
import project_binding as pb
import project_context as pc
import project_lessons as pl
import workflow as w
import model_host as h
import execution_policy

ROLE = 'context-guardian'

def fixture_git_environment():
    return {key: value for key, value in os.environ.items()
            if not key.startswith('GIT_') or key.startswith(('GIT_AUTHOR_', 'GIT_COMMITTER_'))}


def fork_lock_probe(folder, sender):
    try:
        with w.project_lock(folder, reentrant=True):
            sender.send('entered')
    except ValueError:
        sender.send('blocked')
    finally:
        sender.close()


class IndependentContextAcceptance(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=fixture_git_environment())
        _, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'a.py').write_text('def a():\n    return 1\n', encoding='utf-8')
        (self.root / 'criteria.md').write_text('- return 1\n', encoding='utf-8')
        self.enter()
        self.binding = pb.load_binding(self.root)

    def enter(self, task='audit-task', seeds=('a.py',)):
        return pb.enter(self.root, 'audit-project', task, ROLE, seeds=seeds,
                        sources=['a.py'], criteria_path='criteria.md')

    def context(self):
        return pc.load(self.root, {'task_id': 'audit-task'})

    def test_exact_serialized_size_includes_final_metadata(self):
        context = self.context()
        actual = len((pc.canonical(context) + '\n').encode())
        self.assertEqual(context['bytes'], actual)
        config, _ = pb.load_config(self.root)
        self.assertLessEqual(actual, config['budgets']['context_bytes'])

    def test_local_context_metadata_is_ignored_by_git(self):
        result = subprocess.run(['git', 'check-ignore', '.crewloom/binding.json'],
                                cwd=self.root, capture_output=True, text=True, env=fixture_git_environment())
        self.assertEqual(result.returncode, 0, '.crewloom contains local state and must be ignored')
        untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'],
                                            cwd=self.root, text=True, env=fixture_git_environment())
        self.assertNotIn('.crewloom/', untracked)

    def test_changed_criteria_blocks_frozen_context(self):
        (self.root / 'criteria.md').write_text('- return 999\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            pc.require_fresh(self.root, self.binding, 'audit-task')

    def test_large_project_keeps_optional_index_metadata_within_task_budget(self):
        for index in range(600):
            path = self.root / ('unrelated_long_component_navigation_module_%04d.py' % index)
            path.write_text('def helper_%04d():\n    return 1\n' % index, encoding='utf-8')
        self.enter()
        context = self.context()
        config, _ = pb.load_config(self.root)
        self.assertLessEqual(context['bytes'], config['budgets']['context_bytes'])
        self.assertEqual(context['bodies'][0]['text'], (self.root / 'a.py').read_text())
        self.assertIn('a.py', context['navigation']['text'])
        self.assertTrue(context['omissions'])

    def test_dense_dependency_ranges_are_bounded_without_dropping_declared_body(self):
        imports = []
        for index in range(110):
            name = 'dependency_%03d' % index
            imports.append('import ' + name)
            (self.root / (name + '.py')).write_text('\n'.join(
                'def helper_%03d_%02d():\n    return 1\n' % (index, symbol)
                for symbol in range(14)), encoding='utf-8')
        (self.root / 'a.py').write_text('\n'.join(imports) + '\ndef a():\n    return 1\n', encoding='utf-8')
        self.enter()
        context = self.context()
        config, _ = pb.load_config(self.root)
        self.assertLessEqual(context['bytes'], config['budgets']['context_bytes'])
        self.assertEqual(context['bodies'][0]['text'], (self.root / 'a.py').read_text())
        self.assertIn('a.py', context['navigation']['text'])
        self.assertTrue(any(item['kind'] == 'ranges' for item in context['omissions']))

    def test_scoped_index_freshness_uses_the_configured_inventory(self):
        scope = self.root / 'src'
        scope.mkdir()
        (scope / 'entry.py').write_text('def entry():\n    return 1\n', encoding='utf-8')
        config, _ = pb.load_config(self.root)
        config['source_roots'] = ['src']
        config['exclude'].append('ignored')
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        pb.enter(self.root, 'audit-project', 'audit-task', ROLE, seeds=['src/entry.py'],
                 sources=['src/entry.py'], criteria_path='criteria.md')
        pc.require_fresh(self.root, self.binding, 'audit-task')
        (self.root / 'outside.py').write_text('x = 1\n', encoding='utf-8')
        ignored = scope / 'ignored'
        ignored.mkdir()
        (ignored / 'hidden.py').write_text('x = 1\n', encoding='utf-8')
        pc.require_fresh(self.root, self.binding, 'audit-task')
        (scope / 'added.py').write_text('x = 1\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            pc.require_fresh(self.root, self.binding, 'audit-task')

    def test_managed_prompt_receives_full_claude_project_rules(self):
        marker = 'project_rule_marker_must_reach_the_model'
        (self.root / 'CLAUDE.md').write_text('All model outputs must respect ' + marker + '.\n', encoding='utf-8')
        self.enter()
        step = {'id': 'generate', 'role': ROLE, 'summary': 'Return code', 'host': 'openai',
                'kind': 'model', 'inputs': ['a.py'], 'outputs': ['out.py']}
        prompt = h.build_prompt(self.root, step, 'en', 'audit-task')
        self.assertIn(marker, prompt)
        payload = json.loads(prompt.split('\n', 1)[1])
        self.assertEqual(payload['project_context']['navigation']['text'], self.context()['navigation']['text'])

    def test_index_freshness_accepts_unchanged_skipped_non_utf8_source(self):
        (self.root / 'unsupported_encoding.py').write_bytes(b'\xff\xfe\x00binary')
        self.enter()
        pc.require_fresh(self.root, self.binding, 'audit-task')

    def test_native_finish_instruction_uses_executor_evidence(self):
        config, _ = pb.load_config(self.root)
        block = pb.instruction_block(config, self.binding)
        self.assertIn('--evidence', block, 'Successful finish requires executor references, not attestations')
        arguments = shlex.split(block.split('- Exit: `', 1)[1].split('`', 1)[0])
        references = json.loads(arguments[arguments.index('--evidence') + 1])
        self.assertIsInstance(references, list)
        self.assertIn('workflow', references[0])

    def test_freshness_cannot_hide_new_files_beyond_the_scan_cap(self):
        (self.root / 'b.py').write_bytes((self.root / 'a.py').read_bytes())
        with patch('repo_map.MAX_FILES', 2):
            self.enter()
            pc.require_fresh(self.root, self.binding, 'audit-task')
            extra = self.root / 'zz_new.py'
            extra.write_text('def z():\n    return 1\n', encoding='utf-8')
            reads = []
            original_read = Path.read_bytes
            def track_read(path):
                reads.append(path)
                return original_read(path)
            with patch.object(Path, 'read_bytes', track_read):
                with self.assertRaises(ValueError):
                    pc.require_fresh(self.root, self.binding, 'audit-task')
            self.assertNotIn(extra, reads, 'Scan cap must reject before reading the extra source')

    def test_scan_byte_budget_includes_non_utf8_candidates(self):
        raw = b'\xff\xfe\x00binary'
        (self.root / 'unsupported_encoding.py').write_bytes(raw)
        limit = len((self.root / 'a.py').read_bytes()) + len(raw)
        with patch('repo_map.MAX_TOTAL', limit):
            self.enter()
            pc.require_fresh(self.root, self.binding, 'audit-task')
            extra = self.root / 'zz_invalid_encoding.py'
            extra.write_bytes(raw)
            reads = []
            original_read = Path.read_bytes
            def track_read(path):
                reads.append(path)
                return original_read(path)
            with patch.object(Path, 'read_bytes', track_read):
                with self.assertRaises(ValueError):
                    pc.require_fresh(self.root, self.binding, 'audit-task')
            self.assertNotIn(extra, reads, 'Aggregate scan bytes include skipped decoder candidates')

    def test_first_native_adapter_entry_freezes_the_final_project_instructions(self):
        (self.root / 'AGENTS.md').write_text('# Customer constitution\nPreserve this rule.\n', encoding='utf-8')
        config, _ = pb.load_config(self.root)
        config['host_adapter'].update(enabled=True, files=['AGENTS.md'])
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        entered = self.enter()
        pc.require_fresh(self.root, self.binding, 'audit-task')
        self.assertIn('Preserve this rule.', (self.root / 'AGENTS.md').read_text())
        repeated = self.enter()
        self.assertEqual(entered['context']['generation'], repeated['context']['generation'])
        self.assertFalse(repeated['context']['written'])

    def test_model_map_option_honors_the_bound_project_source_roots(self):
        scope = self.root / 'src'
        scope.mkdir()
        (scope / 'entry.py').write_text('def entry():\n    return 1\n', encoding='utf-8')
        (self.root / 'z_outside.py').write_text('def outside():\n    return 1\n', encoding='utf-8')
        config, _ = pb.load_config(self.root)
        config['source_roots'] = ['src']
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        pb.enter(self.root, 'audit-project', 'audit-task', ROLE, seeds=['src/entry.py'],
                 sources=['src/entry.py'], criteria_path='criteria.md')
        step = {'id': 'generate', 'role': ROLE, 'summary': 'Return code', 'host': 'openai',
                'kind': 'model', 'inputs': ['src/entry.py'], 'outputs': ['out.py'], 'repo_map': True}
        with patch('repo_map.MAX_FILES', 2):
            prompt = h.build_prompt(self.root, step, 'en', 'audit-task')
        payload = json.loads(prompt.split('\n', 1)[1])
        self.assertIn('src/entry.py', payload['repo_map']['navigation'])
        self.assertNotIn('z_outside.py', payload['repo_map']['navigation'])

    def test_verified_lesson_selection_respects_actual_serialized_byte_budget(self):
        config, _ = pb.load_config(self.root)
        config['budgets']['lesson_budget_bytes'] = 1024
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        template = {'id': 'fixture', 'state': 'verified', 'issue': 'Observed fixture',
                    'conditions': {}, 'verification': {}, 'negative': False,
                    'source_task': 'audit-task', 'fingerprints': {}, 'command_execution': 'never'}
        selected = [dict(template, id='too-large', remedy='x' * 10000),
                    dict(template, id='small', remedy='A concise verified remedy')]
        with patch.object(pl, 'select', return_value={'lessons': selected,
                          'negative_evidence_count': 0, 'omitted': 0}):
            self.enter()
        context = self.context()
        self.assertLessEqual(len(pc.canonical(context['lessons']).encode()), 1024)
        self.assertIn('small', [lesson['id'] for lesson in context['lessons']])
        self.assertTrue(any(item['kind'] == 'lessons' and item['count'] for item in context['omissions']))
        self.assertEqual(context['bodies'][0]['text'], (self.root / 'a.py').read_text())

    def test_required_source_larger_than_context_budget_is_rejected_before_read(self):
        oversized = self.root / 'oversized.py'
        oversized.write_text('x = "' + 'x' * 40000 + '"\n', encoding='utf-8')
        config, _ = pb.load_config(self.root)
        reads = []
        original_read = Path.read_bytes
        def track_read(path):
            reads.append(path)
            return original_read(path)
        with patch.object(Path, 'read_bytes', track_read):
            with self.assertRaises(ValueError):
                pc.snapshot(self.root, self.binding, 'audit-task', ROLE, config, [],
                            ['oversized.py'], 'en', ['oversized.py'])
        self.assertNotIn(oversized, reads, 'An oversized required body must fail before loading its bytes')

    def test_project_entry_automatically_invalidates_stale_verified_lesson_sources(self):
        pb.cancel(self.root, 'audit-project', 'audit-task', 'prepare lesson expiry fixture')
        plan = {'schema_version': 1, 'id': 'lesson-expiry-proof', 'steps': [
            {'id': 'check', 'role': ROLE, 'summary': 'Check declared source',
             'argv': ['python3', '-c', 'pass'], 'inputs': ['a.py'], 'outputs': ['proof.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        def command(root, step, image, timeout):
            (root / 'proof.txt').write_text('objective fixture acceptance', encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image}
        with patch.object(w, 'inspect_image', return_value='sha256:unit-fixture'), \
                patch.object(execution_policy, 'execute', side_effect=command):
            self.assertEqual(w.run(self.root, parsed, fingerprint, 'fixture')['status'], 'complete')
        lesson = pl.record(self.root, self.binding, 'a.py source condition', 'Reuse only matching verified sources',
                           conditions={'paths': ['a.py']}, declared=['a.py'])['lesson']
        self.assertEqual(pl.verify(self.root, lesson['id'], [{'workflow': plan['id'], 'step': 'check'}])['state'], 'verified')
        (self.root / 'a.py').write_text('def a():\n    return 99\n', encoding='utf-8')
        self.enter(task='after-source-change')
        context = pc.load(self.root, {'task_id': 'after-source-change'})
        self.assertNotIn(lesson['id'], [item['id'] for item in context['lessons']])
        self.assertEqual(pl.read(self.root, lesson['id'])['state'], 'invalidated')

    def test_failed_context_start_reservation_can_be_explicitly_cancelled(self):
        pb.cancel(self.root, 'audit-project', 'audit-task', 'prepare failed entry fixture')
        config, _ = pb.load_config(self.root)
        config['policy'].update(mode='enforced', managed_lifecycle=True)
        config['budgets']['context_bytes'] = 4096
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        original = 'x = "' + 'x' * 20000 + '"\n'
        (self.root / 'a.py').write_text(original, encoding='utf-8')
        plan = {'schema_version': 1, 'id': 'failed-context-start', 'steps': [
            {'id': 'check', 'role': ROLE, 'summary': 'Prepare a context that exceeds its budget',
             'argv': ['python3', '-c', 'pass'], 'inputs': ['a.py'], 'outputs': ['out.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        with self.assertRaises(ValueError):
            w.run(self.root, parsed, fingerprint, 'fixture')
        self.assertEqual(w.active_workflow(self.root)['workflow'], plan['id'])
        cancelled = w.cancel(self.root, parsed, fingerprint)
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertIsNone(w.active_workflow(self.root))
        self.assertIsNone(pb.reservation(self.root))
        self.assertEqual((self.root / 'a.py').read_text(), original)

    def test_changed_config_blocks_frozen_context(self):
        config, _ = pb.load_config(self.root)
        config['budgets']['map_bytes'] = 4096
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        with self.assertRaises(ValueError):
            pc.require_fresh(self.root, self.binding, 'audit-task')

    def test_claimed_command_exit_does_not_complete_task(self):
        report = pb.finish(self.root, 'audit-project', 'audit-task', verification=[
            {'command': ['python3', '-c', 'raise RuntimeError()'], 'exit_code': 0}])
        self.assertEqual(report['status'], 'awaiting_verification')
        self.assertFalse(report['verified'])

    def test_workflow_state_without_executor_ledger_cannot_promote(self):
        lesson = pl.record(self.root, self.binding, 'Unsupported success', 'Run a real check')['lesson']
        directory = self.root / '.crewloom/workflows/forged-flow'
        directory.mkdir(parents=True)
        (directory / 'state.json').write_text(json.dumps({
            'workflow': 'forged-flow', 'project_root': str(self.root),
            'project_id': self.binding['project_id'], 'checkout_id': self.binding['checkout_id'],
            'steps': {'check': {'kind': 'command', 'argv': ['python3', '-c', 'pass'],
                                'status': 'complete', 'attempts': [{'status': 'finished', 'exit_code': 0}],
                                'inputs': {}, 'outputs': {}}}}), encoding='utf-8')
        with self.assertRaises(ValueError):
            pl.verify(self.root, lesson['id'], [{'workflow': 'forged-flow', 'step': 'check'}])
        self.assertEqual(pl.read(self.root, lesson['id'])['state'], 'candidate')

    def test_unchanged_entry_after_edit_reuses_new_generation(self):
        (self.root / 'a.py').write_text('def a():\n    return 22\n', encoding='utf-8')
        edited = self.enter()['context']
        repeated = self.enter()['context']
        self.assertEqual(repeated['generation'], edited['generation'])
        self.assertFalse(repeated['written'])

    def test_rejected_task_does_not_write_project_metadata(self):
        def fingerprints():
            return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (self.root / '.crewloom').rglob('*') if path.is_file()}
        before = fingerprints()
        with self.assertRaises(ValueError):
            self.enter(task='other-task')
        self.assertEqual(fingerprints(), before)

    def test_same_content_files_have_distinct_resolvable_range_keys(self):
        (self.root / 'b.py').write_bytes((self.root / 'a.py').read_bytes())
        self.enter(seeds=['a.py', 'b.py'])
        context = self.context()
        ranges = [item for item in context['ranges'] if item['path'] in ('a.py', 'b.py')]
        self.assertEqual(len(ranges), 2)
        self.assertEqual(len({item['cache_key'] for item in ranges}), 2)
        for item in ranges:
            text = pc.resolve_range(self.root, context, item['cache_key'], item['path'],
                                    item['start'], item['end'])
            self.assertIn('return 1', text)

    def test_range_cannot_be_resolved_in_another_identical_project_root(self):
        context = self.context()
        item = next(entry for entry in context['ranges'] if entry['path'] == 'a.py')
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder).resolve()
            (other / 'a.py').write_bytes((self.root / 'a.py').read_bytes())
            with self.assertRaises(ValueError):
                pc.resolve_range(other, context, item['cache_key'], item['path'], item['start'], item['end'])

    def test_managed_model_receives_verified_lesson_and_frozen_scope(self):
        pb.cancel(self.root, 'audit-project', 'audit-task', 'prepare managed fixture')
        config, _ = pb.load_config(self.root)
        config['policy'].update(mode='enforced', managed_lifecycle=True)
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')

        def command(root, step, image, timeout):
            for name in step['outputs']:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('fixture acceptance evidence', encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image}

        def run_plan(plan):
            filename = plan['id'] + '.json'
            (self.root / filename).write_text(json.dumps(plan), encoding='utf-8')
            parsed, fingerprint = w.read_plan(self.root, filename)
            with patch.object(w, 'inspect_image', return_value='sha256:unit-fixture'), \
                    patch.object(execution_policy, 'execute', side_effect=command):
                return w.run(self.root, parsed, fingerprint, 'fixture')

        proof = {'schema_version': 1, 'id': 'learning-proof', 'criteria': 'criteria.md', 'steps': [
            {'id': 'check', 'role': ROLE, 'summary': 'Fixture command acceptance',
             'argv': ['python3', '-c', 'pass'], 'inputs': ['a.py'], 'outputs': ['proof.txt']}]}
        self.assertEqual(run_plan(proof)['status'], 'complete')
        marker = 'verified_remedy_must_reach_the_model'
        lesson = pl.record(self.root, pb.load_binding(self.root), 'a.py fixture navigation', marker,
                           conditions={'paths': ['a.py']}, declared=['a.py'])['lesson']
        verified = pl.verify(self.root, lesson['id'], [{'workflow': 'learning-proof', 'step': 'check'}])
        self.assertEqual(verified['state'], 'verified')
        captured = []

        def generate(host, prompt, outputs, *args, **kwargs):
            captured.append(prompt)
            return {outputs[0]: 'def generated():\n    return 1\n'}, {'host': host}

        model = {'schema_version': 1, 'id': 'model-context-audit', 'criteria': 'criteria.md', 'steps': [
            {'id': 'generate', 'role': ROLE, 'kind': 'model', 'host': 'openai',
             'summary': 'Use verified project navigation lessons', 'inputs': ['a.py'],
             'outputs': ['generated.py']},
            {'id': 'acceptance', 'role': ROLE, 'summary': 'Fixture generated artifact check',
             'argv': ['python3', '-c', 'pass'], 'inputs': ['generated.py'], 'outputs': ['accepted.txt']}]}
        with patch.object(h, 'generate', side_effect=generate):
            result = run_plan(model)
            repeated = run_plan(model)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(repeated['status'], 'complete')
        self.assertEqual(len(captured), 1)
        self.assertIn(marker, captured[0])
        self.assertIn(self.binding['project_id'], captured[0])
        self.assertIn(self.binding['checkout_id'], captured[0])
        original = pc.history_path(self.root, 'model-context-audit', 1)
        snapshot = json.loads(original.read_text()) if original.exists() else pc.load(
            self.root, {'task_id': 'model-context-audit'}, verify_hashes=False)
        self.assertIn(snapshot['semantic_sha256'], captured[0])

    def test_two_model_steps_with_same_inputs_reuse_their_own_consumed_generations(self):
        pb.cancel(self.root, 'audit-project', 'audit-task', 'prepare multi-step fixture')
        config, _ = pb.load_config(self.root)
        config['policy'].update(mode='enforced', managed_lifecycle=True)
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        plan = {'schema_version': 1, 'id': 'two-model-steps', 'criteria': 'criteria.md', 'steps': [
            {'id': name, 'role': ROLE, 'kind': 'model', 'host': 'openai',
             'summary': 'Generate ' + name, 'inputs': ['a.py'], 'outputs': [name + '.py']}
            for name in ('first', 'second')] + [
            {'id': 'acceptance', 'role': ROLE, 'summary': 'Check both generated artifacts',
             'argv': ['python3', '-c', 'pass'], 'inputs': ['first.py', 'second.py'],
             'outputs': ['accepted.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        captured = []
        def generate(host, prompt, outputs, *args, **kwargs):
            captured.append(prompt)
            return {name: 'def generated():\n    return 1\n' for name in outputs}, {'host': host}
        def command(root, step, image, timeout):
            for name in step['outputs']:
                (root / name).write_text('objective fixture acceptance', encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image}
        with patch.object(w, 'inspect_image', return_value='sha256:unit-fixture'), \
                patch.object(execution_policy, 'execute', side_effect=command), \
                patch.object(h, 'generate', side_effect=generate):
            initial = w.run(self.root, parsed, fingerprint, 'fixture')
            repeated = w.run(self.root, parsed, fingerprint, 'fixture')
        self.assertEqual(initial['status'], 'complete')
        self.assertEqual(repeated['status'], 'complete')
        self.assertEqual(len(captured), 2, 'Each completed model step must reuse its own consumed evidence')

    @unittest.skipUnless('fork' in multiprocessing.get_all_start_methods(), 'fork not available')
    def test_forked_process_cannot_inherit_reentrant_lock_ownership(self):
        runtime = self.root / '.crewloom'
        process_context = multiprocessing.get_context('fork')
        receiver, sender = process_context.Pipe(duplex=False)
        self.addCleanup(receiver.close)
        with w.project_lock(runtime, reentrant=True):
            process = process_context.Process(target=fork_lock_probe, args=(runtime, sender))
            process.start()
            sender.close()
            try:
                self.assertTrue(receiver.poll(5), 'child failed to report lock result')
                self.assertEqual(receiver.recv(), 'blocked')
            finally:
                process.join(5)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
            self.assertTrue((runtime / 'lock').is_file())
        self.assertFalse((runtime / 'lock').exists())


    def test_pilot_stability_compares_resealed_timing(self):
        import context_pilot as pilot
        original = self.context()
        observations = []
        for duration in (9, 1234567):
            context = json.loads(json.dumps(original))
            context['telemetry']['duration_ms'] = duration
            context = pc.seal(context)
            self.assertEqual(context['bytes'], pc.payload_bytes(context))
            observations.append((context, pilot.stable_payload(context)))
        narrow, wide = observations
        self.assertEqual(wide[0]['bytes'] - narrow[0]['bytes'], 6)
        self.assertEqual(narrow[1]['stable_sha256'], wide[1]['stable_sha256'])
        self.assertEqual(narrow[1]['stable_semantic_sha256'], wide[1]['stable_semantic_sha256'])
        self.assertEqual(narrow[0]['bytes'] - narrow[1]['volatile_bytes'],
                         wide[0]['bytes'] - wide[1]['volatile_bytes'])
        changed = json.loads(json.dumps(wide[0]))
        changed['bodies'][0]['text'] += '\nactual source change\n'
        changed = pc.seal(changed)
        self.assertNotEqual(pilot.stable_payload(changed)['stable_sha256'],
                            wide[1]['stable_sha256'])


    def test_git_map_ignores_foreign_repository_environment(self):
        import repo_map
        parent_index = self.root / '.git/index'
        subprocess.run(['git', 'add', 'a.py'], cwd=self.root, check=True,
                       env=fixture_git_environment())
        protected = {name: (self.root / '.git' / name).read_bytes()
                     for name in ('HEAD', 'index', 'config')}
        with tempfile.TemporaryDirectory() as folder:
            selected = Path(folder).resolve()
            subprocess.run(['git', 'init', '-q'], cwd=selected, check=True,
                           env=fixture_git_environment())
            (selected / 'selected.py').write_text('def selected():\n    return 9\n')
            poison = {'GIT_DIR': str(self.root / '.git'), 'GIT_WORK_TREE': str(self.root),
                      'GIT_INDEX_FILE': str(parent_index), 'GIT_COMMON_DIR': str(self.root / '.git'),
                      'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.worktree',
                      'GIT_CONFIG_VALUE_0': str(self.root)}
            with patch.dict(os.environ, poison):
                value, stats = repo_map.build(selected)
            self.assertEqual(set(value['files']), {'selected.py'})
            self.assertEqual(stats['head'], '')
            self.assertEqual(value['project_root'], str(selected))
        self.assertEqual(protected, {name: (self.root / '.git' / name).read_bytes()
                                     for name in protected})

    def test_foreign_git_environment_cannot_turn_plain_directory_into_project(self):
        import repo_map
        with tempfile.TemporaryDirectory() as folder:
            plain = Path(folder).resolve()
            (plain / 'plain.py').write_text('x = 1\n')
            poison = {'GIT_DIR': str(self.root / '.git'), 'GIT_WORK_TREE': str(self.root),
                      'GIT_INDEX_FILE': str(self.root / '.git/index')}
            with patch.dict(os.environ, poison):
                with self.assertRaisesRegex(ValueError, 'Git project'):
                    repo_map.build(plain)
            self.assertFalse((plain / '.git').exists())
            self.assertFalse((plain / '.crewloom').exists())


if __name__ == '__main__':
    unittest.main()
