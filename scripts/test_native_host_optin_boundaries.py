"""Every native CLI requires explicit operator opt-in before generation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import model_host
import workflow


class NativeHostOptInBoundaries(unittest.TestCase):
    def test_opencode_is_refused_before_provider_or_output_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            (root/'task.md').write_text('Implement a small feature',encoding='utf-8')
            role=root/'.agents/skills/fullstack-mvp-engineer'
            (role/'brain').mkdir(parents=True)
            (role/'SKILL.md').write_text('Use only declared inputs',encoding='utf-8')
            for name in workflow.MEMORY:
                (role/'brain'/(name+'.md')).write_text('# Project memory',encoding='utf-8')
            plan={'schema_version':1,'id':'native-optin-test','steps':[{
                'id':'generate','role':'fullstack-mvp-engineer','kind':'model','host':'opencode',
                'summary':'Implement a feature','inputs':['task.md'],'outputs':['src/result.py']}]}
            (root/'workflow.json').write_text(json.dumps(plan),encoding='utf-8')
            loaded,fingerprint=workflow.read_plan(root,'workflow.json')
            with patch.object(model_host,'generate',return_value=({'src/result.py':'value=1\n'},{'host':'opencode'})) as generate:
                result=workflow.run(root,loaded,fingerprint,'fixture-image')
            self.assertEqual(result['status'],'failed',result)
            self.assertIn('allow-host-cli',result['blocker'])
            generate.assert_not_called()
            self.assertFalse((root/'src/result.py').exists())


if __name__=='__main__':
    unittest.main()
