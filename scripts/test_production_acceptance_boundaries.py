"""Independent adversarial checks for production review authorization boundaries."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

import project_binding as pb
import reviewer_credentials as reviewers
import crewloom_resources as resources
import execution_policy as broker
import workflow as workflow
import crewloom
import project_context as project_context
import repo_map


class CredentialReviewBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        pb.bootstrap(self.root, project_id='review-boundary-pilot')
        config_path = self.root / 'crewloom.project.json'
        config = json.loads(config_path.read_text())
        config['policy']['review'] = {'mode': 'verified', 'allow_self_review': False}
        config_path.write_text(json.dumps(config))
        pb.bootstrap(self.root, project_id='review-boundary-pilot')
        self.principal, self.token = reviewers.register(self.root, 'independent-reviewer')
        self.step = {'id': 'build', 'role': 'fullstack-mvp-engineer'}
        self.outputs = {'output.txt': 'a' * 64}
        self.workflow_id = 'review-pilot'

    def authorize(self):
        return reviewers.authorize(self.root, self.workflow_id, self.step,
                                   self.outputs, token=self.token)

    def verify(self, proof, outputs=None, workflow_id=None):
        return reviewers.verify_record(
            self.root, {'review': proof}, self.step, workflow_id or self.workflow_id,
            self.outputs if outputs is None else outputs,
            method=reviewers.CREDENTIAL_METHOD)

    def assert_refused(self, proof, **kwargs):
        self.assertNotEqual(self.verify(proof, **kwargs), 'valid')

    def test_real_credential_authorizes_its_exact_scope(self):
        proof = self.authorize()
        self.assertEqual(self.verify(proof), 'valid')
        self.assertNotIn(self.token, json.dumps(proof))
        self.assertNotIn(self.token, reviewers.registry_path(self.root).read_text())

    def test_recomputed_public_checksum_cannot_forge_principal(self):
        forged = copy.deepcopy(self.authorize())
        forged['principal'] = 'never-registered'
        if hasattr(reviewers, 'proof_digest'):
            forged['proof_sha256'] = reviewers.proof_digest(forged)
        self.assert_refused(forged)

    def test_revocation_invalidates_previously_authorized_record(self):
        proof = self.authorize()
        reviewers.revoke(self.root, self.principal)
        self.assert_refused(proof)

    def test_recomputed_public_checksum_cannot_refresh_decision_time(self):
        forged = copy.deepcopy(self.authorize())
        forged['decided_at'] = '2099-01-01T00:00:00+00:00'
        if hasattr(reviewers, 'proof_digest'):
            forged['proof_sha256'] = reviewers.proof_digest(forged)
        self.assert_refused(forged)

    def test_proof_cannot_authorize_another_task_or_artifact(self):
        proof = self.authorize()
        self.assert_refused(proof, workflow_id='different-task')
        self.assert_refused(proof, outputs={'output.txt': 'b' * 64})

    def test_reissued_credential_invalidates_prior_approval(self):
        proof = self.authorize()
        reviewers.register(self.root, self.principal)
        self.assert_refused(proof)

    def test_candidate_cannot_read_or_replace_review_issuance_authority(self):
        registry = reviewers.registry_path(self.root)
        relative = registry.relative_to(self.root).as_posix()
        with self.assertRaises(ValueError):
            workflow.hashes(self.root, [relative])
        with self.assertRaises(ValueError):
            broker.destinations(self.root, [relative])

    def test_review_signing_material_cannot_leave_in_declared_context_body(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.root,
                       env=repo_map.git_environment(), check=True)
        installed, errors = crewloom.install_skills(
            self.root, 'agents', [self.step['role']], False)
        self.assertFalse(errors)
        self.assertIn(self.step['role'], installed)
        state = pb.bootstrap(self.root, project_id='review-boundary-pilot')
        relative = reviewers.registry_path(self.root).relative_to(self.root).as_posix()
        with self.assertRaises(ValueError):
            project_context.snapshot(self.root, state['binding'], 'secret-context-pilot',
                                     self.step['role'], state['config'], [], [], declared=[relative])

    @unittest.skipUnless(os.name == 'posix', 'POSIX owner-only issuance authority mode')
    def test_world_readable_issuance_authority_fails_closed(self):
        proof = self.authorize()
        reviewers.registry_path(self.root).chmod(0o644)
        self.assert_refused(proof)


class InstalledRuntimeBrokerBoundaries(unittest.TestCase):
    def test_module_root_is_protected_separately_from_packaged_role_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            modules = root / 'local-venv' / 'site-packages'
            data = modules / 'crewloom_data'
            data.mkdir(parents=True)
            runtime = modules / 'workflow.py'
            runtime.write_text('# installed trusted runtime\n')
            with patch.object(workflow, 'LIBRARY', data), patch.object(
                    resources, 'installed_roots', return_value=(data, modules)):
                with self.assertRaisesRegex(ValueError, 'Trusted|runtime|read-only'):
                    broker.destinations(root, [runtime.relative_to(root).as_posix()])
            self.assertEqual(runtime.read_text(), '# installed trusted runtime\n')


class DashboardCredentialPathBoundaries(unittest.TestCase):
    def test_a_preexisting_temporary_symlink_cannot_redirect_secret_writes(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as foreign_directory:
            root = Path(directory).resolve()
            foreign = Path(foreign_directory).resolve() / 'protected.txt'
            foreign.write_text('foreign project must remain unchanged\n')
            (root / '.crewloom').mkdir()
            (root / '.crewloom' / 'dashboard-token.tmp').symlink_to(foreign)
            try:
                crewloom.write_dashboard_secret(root, 'synthetic-fixture-secret-01234567890123456789')
            except ValueError:
                pass
            self.assertEqual(foreign.read_text(), 'foreign project must remain unchanged\n')


if __name__ == '__main__':
    unittest.main()
