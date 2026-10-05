"""Native acceptance contract immutability, receipt honesty and exact UTF-8 context budgets.

Every case here is offline and binds one disposable project. No host provider is called, no Docker
container runs and no global configuration is written; the acceptance runner is either refused
before it is reached or replaced by a mock whose only job is to prove it was never invoked. The
frozen independent boundaries live in `test_native_contract_boundaries.py`; this file covers the
same three requirements from the producer side, with the cases that suite cannot express: physical
and resolved aliases, a contract file that disappears, a callback that must write nothing at all,
status that separates an altered contract from an intact hook payload, and mandatory overflow that
is refused before a single optional body is even considered.
"""
import json
import unittest
from unittest.mock import Mock, patch

import host_lifecycle as hl
import project_binding as pb
import test_host_lifecycle as fixture
import workflow as w


class NativeAcceptanceContractBoundaries(fixture.Fixture):
    """Install-time and runtime pinning of the immutable acceptance contract."""

    def snapshot(self):
        return {str(item.relative_to(self.root)): item.read_bytes()
                for item in self.root.rglob('*') if item.is_file() and '.git' not in item.parts}

    def pinned(self, record=None):
        record = record or hl.load_install(self.root, 'codex')
        return [item['path'] for item in record['acceptance_inputs']]

    def refuse_output(self, name, message='immutable authority'):
        before = self.snapshot()
        with self.assertRaisesRegex(hl.LifecycleError, message):
            self.install(outputs=(name,))
        self.assertEqual(self.snapshot(), before,
                         'an invalid acceptance contract must not partly write this installation')

    def test_the_plan_the_criteria_and_every_declared_checker_are_pinned_by_content(self):
        record = self.install()
        pinned = self.pinned(record)
        self.assertIn(fixture.CRITERIA, pinned)
        self.assertIn(fixture.ACCEPTANCE_PLAN, pinned)
        for name in ('tests/__init__.py', 'tests/test_login.py', 'tests/test_acceptance.py',
                     'src/__init__.py'):
            self.assertIn(name, pinned, name)
        for item in record['acceptance_inputs']:
            self.assertEqual(hl.digest((self.root / item['path']).read_bytes()), item['sha256'],
                             item['path'])

    def test_the_plan_criteria_path_and_the_explicit_criteria_are_both_tracked(self):
        (self.root / 'plan-criteria.md').write_text('- the plan names its own criteria\n',
                                                    encoding='utf-8')
        plan = json.loads((self.root / fixture.ACCEPTANCE_PLAN).read_text(encoding='utf-8'))
        plan['criteria'] = 'plan-criteria.md'
        (self.root / fixture.ACCEPTANCE_PLAN).write_text(json.dumps(plan), encoding='utf-8')
        record = self.install()
        self.assertEqual(self.pinned(record), sorted(
            ['plan-criteria.md', fixture.ACCEPTANCE_PLAN, 'tests/__init__.py',
             'tests/test_acceptance.py', 'tests/test_login.py', fixture.CRITERIA, 'src/__init__.py']))

    def test_a_case_alias_of_the_criteria_is_never_a_declared_output(self):
        self.refuse_output('CRITERIA.MD')

    def test_a_resolved_parent_spelling_of_a_checker_is_never_a_declared_output(self):
        # `tests/../tests/test_login.py` names one file without ever spelling it, so the folded key
        # cannot see it and the resolved device and inode can.
        self.refuse_output('tests/../tests/test_login.py')

    def test_a_declared_output_reaching_a_checker_through_a_symlinked_directory_is_refused(self):
        (self.root / 'alias').symlink_to(self.root / 'tests')
        self.refuse_output('alias/test_login.py')

    def test_a_missing_declared_acceptance_input_is_refused_before_any_write(self):
        (self.root / 'tests' / 'test_login.py').unlink()
        self.refuse_output(fixture.DECLARED, 'Acceptance contract input is missing')

    def test_the_source_under_test_is_never_pinned_and_stays_editable(self):
        record = self.install(outputs=(fixture.SOURCE_FILE, fixture.DECLARED))
        self.assertNotIn(fixture.SOURCE_FILE, self.pinned(record),
                         'the candidate under test must stay editable')
        hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        with (self.root / fixture.SOURCE_FILE).open('a') as stream:
            stream.write('\n# A real candidate edit\n')
        self.assertEqual(hl.acceptance_drift(self.root, record), [])

    def test_an_ordinary_file_outside_the_configured_acceptance_is_not_invented_immutable(self):
        record = self.install()
        (self.root / 'docs').mkdir()
        (self.root / 'docs' / 'notes.md').write_text('not part of the acceptance\n', encoding='utf-8')
        self.assertEqual(hl.acceptance_drift(self.root, record), [])
        self.assertEqual(hl.require_acceptance_contract(self.root, record), True)

    def test_a_deleted_contract_file_is_drift_and_never_a_silent_adoption(self):
        record = self.install()
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        (self.root / fixture.CRITERIA).unlink()
        self.assertEqual(hl.acceptance_drift(self.root, record), [fixture.CRITERIA])
        runner = Mock(side_effect=ValueError('The forbidden runner was reached'))
        with self.assertRaisesRegex(hl.LifecycleError, 'altered after install'):
            hl.verify(self.root, fixture.PROJECT, record, injected['task_id'], 'Stop', runner=runner)
        runner.assert_not_called()

    def test_contract_drift_refuses_a_callback_before_any_state_is_written(self):
        record = self.install()
        hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        (self.root / fixture.CRITERIA).write_text('- login returns the submitted user, silently\n',
                                                  encoding='utf-8')
        before = self.snapshot()
        with self.assertRaisesRegex(hl.LifecycleError, 'altered after install'):
            hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        self.assertEqual(self.snapshot(), before,
                         'an altered acceptance contract wrote project state before refusing')

    def test_drift_refuses_before_the_reservation_is_released_and_before_the_executor_runs(self):
        record = self.install()
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        held = pb.reservation(self.root)
        with (self.root / fixture.CRITERIA).open('a') as stream:
            stream.write('\n# Externally relaxed\n')
        runner = Mock(side_effect=ValueError('The forbidden runner was reached'))
        with self.assertRaisesRegex(hl.LifecycleError, 'a reviewed reinstall is required'):
            hl.verify(self.root, fixture.PROJECT, record, injected['task_id'], 'Stop', runner=runner)
        runner.assert_not_called()
        self.assertEqual(pb.reservation(self.root), held, 'the reservation was released on a refusal')

    def test_finalization_revalidates_the_contract_after_the_executor_reports_complete(self):
        record = self.install()
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        complete = {'status': 'complete', 'steps': {'acceptance': {'status': 'complete',
                                                                   'attempts': [{'attempt': 1}]}}}

        def altering_runner(root, plan, fingerprint, image):
            with (root / fixture.CRITERIA).open('a') as stream:
                stream.write('\n# Changed while acceptance ran\n')
            return complete

        with patch.object(hl.w, 'state_for', return_value=({'folder': None}, complete)), \
                patch.object(hl.pb, 'finish') as final:
            with self.assertRaisesRegex(hl.LifecycleError, 'altered after install'):
                hl.verify(self.root, fixture.PROJECT, record, injected['task_id'], 'Stop',
                          runner=altering_runner)
        final.assert_not_called()

    def test_status_separates_an_altered_contract_from_an_intact_hook_payload(self):
        self.install()
        intact = hl.status(self.root, fixture.PROJECT, 'codex')
        self.assertTrue(intact['content_intact'])
        self.assertTrue(intact['acceptance_contract_intact'])
        self.assertEqual(intact['altered_acceptance_inputs'], [])
        self.assertFalse(intact['acceptance_contract_altered'])
        with (self.root / fixture.ACCEPTANCE_PLAN).open('a') as stream:
            stream.write('\n')
        altered = hl.status(self.root, fixture.PROJECT, 'codex')
        self.assertTrue(altered['content_intact'], 'the hook payload is untouched by a contract edit')
        self.assertFalse(altered['acceptance_contract_intact'])
        self.assertTrue(altered['acceptance_contract_altered'])
        self.assertEqual(altered['altered_acceptance_inputs'], [fixture.ACCEPTANCE_PLAN])
        self.assertNotEqual(altered['lifecycle'], 'altered',
                            'an altered hook payload is a different fact from an altered contract')

    def test_a_reviewed_reinstall_pins_the_reviewed_bytes_and_clears_the_drift(self):
        first = self.install()
        with (self.root / fixture.CRITERIA).open('a') as stream:
            stream.write('\n# A reviewed criteria change\n')
        self.assertTrue(hl.status(self.root, fixture.PROJECT, 'codex')['acceptance_contract_altered'])
        record = self.install()
        self.assertNotEqual(record['install_id'], first['install_id'],
                            'a reviewed contract change is a new installation, not a silent adoption')
        report = hl.status(self.root, fixture.PROJECT, 'codex')
        self.assertTrue(report['acceptance_contract_intact'])
        self.assertEqual(report['altered_acceptance_inputs'], [])
        self.assertEqual(hl.acceptance_drift(self.root, record), [])


class NativeReceiptBoundaries(fixture.Fixture):
    """The injected receipt reports delivery and nothing else."""

    def test_the_receipt_names_itself_and_disclaims_every_outcome(self):
        record = self.install(acceptance=False)
        receipt = hl.marker_text(record).lower()
        self.assertIn(record['marker'], receipt)
        self.assertIn('receipt', receipt)
        self.assertIn('not completion', receipt)
        self.assertIn('not verification', receipt)
        self.assertIn('not executor', receipt)
        self.assertNotIn('only after', receipt)

    def test_no_injected_line_binds_the_receipt_to_task_completion(self):
        record = self.install(acceptance=False)
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        context = injected['additionalContext'].lower()
        self.assertNotIn('when the task is complete', context)
        self.assertNotIn('only after', context)
        self.assertIn('receipt', context)
        self.assertFalse(hl.status(self.root, fixture.PROJECT, 'codex')['verified_executor'])

    def test_a_reported_receipt_never_reaches_the_project_task_log(self):
        record = self.install(acceptance=False)
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        self.assertIn('delivery receipt', injected['additionalContext'])
        logged = (self.root / hl.STATE_RELATIVE / 'codex' / 'events.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('delivery receipt', logged)
        self.assertNotIn(injected['additionalContext'], logged)
        self.assertEqual(record['marker'], hl.load_install(self.root, 'codex')['marker'])


class NativeContextBudgetBoundaries(fixture.Fixture):
    """The reported budget is the exact UTF-8 length of the payload actually returned."""

    def context(self, record, **overrides):
        value = {'generation': 1, 'semantic_sha256': 'f' * 64, 'criteria': ['retain acceptance'],
                 'rules': []}
        value.update(overrides)
        return value

    def build(self, record, bodies, limit, **overrides):
        record = dict(record, additional_context_limit=limit)
        with patch.object(hl.pc, 'bodies', return_value=bodies):
            return hl.injected_context(self.root, {'checkout_id': record['checkout_id']},
                                       record, self.context(record, **overrides))

    def test_the_reported_bytes_are_the_exact_utf8_length_of_the_returned_payload(self):
        record = self.install(acceptance=False)
        for text, limit in (('x' * 900, 65536), ('عربي' * 900, 65536), ('x' * 4000, 65536),
                            ('عربي' * 4000, 65536)):
            with self.subTest(text=text[:4], limit=limit):
                result = self.build(record, {'src/input.py': {'text': text}}, limit)
                actual = len(result['additionalContext'].encode('utf-8'))
                self.assertEqual(result['bytes'], actual)
                self.assertLessEqual(actual, limit)
                self.assertIn(text, result['additionalContext'])

    def test_mandatory_overflow_is_refused_before_any_optional_body_is_considered(self):
        record = self.install(acceptance=False)
        consulted = Mock(return_value={'src/input.py': {'text': 'never read'}})
        record = dict(record, additional_context_limit=256)
        with patch.object(hl.pc, 'bodies', consulted):
            with self.assertRaisesRegex(hl.LifecycleError, 'delivery receipt alone exceed'):
                hl.injected_context(self.root, {'checkout_id': record['checkout_id']},
                                    record, self.context(record))
        consulted.assert_not_called()

    def test_every_body_that_fits_is_included_whole_and_the_rest_is_an_explicit_omission(self):
        record = self.install(acceptance=False)
        small = 'def login(user):\n    return user\n'
        large = 'y' * 20000
        result = self.build(record, {'src/big.py': {'text': large},
                                     'src/small.py': {'text': small}}, 1024)
        actual = len(result['additionalContext'].encode('utf-8'))
        self.assertEqual(result['bytes'], actual)
        self.assertLessEqual(actual, 1024)
        self.assertIn(small, result['additionalContext'], 'a whole fitting body must be included')
        self.assertNotIn(large, result['additionalContext'], 'an omitted body is never partly sent')
        self.assertEqual([item['path'] for item in result['omissions']], ['src/big.py'])
        self.assertEqual(result['omissions'][0]['bytes'], len(('\n\n### Declared source: src/big.py'
                                                                '\n\n```py\n' + large
                                                                + '\n```').encode('utf-8')))

    def test_the_budget_is_measured_in_utf8_bytes_not_characters(self):
        record = self.install(acceptance=False)
        one = self.build(record, {'src/input.py': {'text': 'عربي' * 25}}, 65536)
        latin = self.build(record, {'src/input.py': {'text': 'a' * 100}}, 65536)
        self.assertEqual(len('عربي' * 25), 100, 'both bodies are the same character count')
        self.assertGreater(one['bytes'], latin['bytes'],
                           'the same character count costs more UTF-8 bytes in Arabic')
        self.assertEqual(one['bytes'], len(one['additionalContext'].encode('utf-8')))

    def test_the_bounded_logged_payload_keeps_the_omission_record_and_not_the_body(self):
        record = self.install(acceptance=False)
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        self.assertEqual(injected['context_bytes'],
                         len(injected['additionalContext'].encode('utf-8')))
        logged = [item for item in hl.observed_events(self.root, 'codex')
                  if item.get('stage') == 'inject']
        self.assertEqual(logged[0]['context_bytes'], injected['context_bytes'])
        self.assertNotIn('additionalContext', logged[0])
        self.assertEqual(logged[0]['omissions'], [])


class NativeAcceptanceExecutorShape(unittest.TestCase):
    """Acceptance still runs through the one shared managed executor; no new evidence source."""

    def test_the_configured_acceptance_still_names_the_shared_managed_ledger(self):
        self.assertEqual(w.DEFAULT_IMAGE, 'python:3.14-slim')
        source = hl.verify.__doc__
        self.assertIn('real Docker executor ledger', source)
        self.assertIn('is never success', source)


if __name__ == '__main__':
    unittest.main()
