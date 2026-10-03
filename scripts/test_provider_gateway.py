"""Tool-free RPC contracts and failure-before-write enforcement."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import model_host as h
import provider_gateway as g
import workflow as w


class GatewayTests(unittest.TestCase):
    def artifacts(self):return json.dumps({'artifacts':[{'path':'a','content':'verified'}]})

    def test_openai_completed_artifacts(self):
        value={'status':'completed','model':'explicit-model','output':[{'type':'message','content':[{'type':'output_text','text':self.artifacts()}]}]}
        artifacts,evidence=g.parse('openai',value,['a']);self.assertEqual(artifacts['a'],'verified')
        self.assertEqual(evidence['model_reported'],'explicit-model')

    def test_anthropic_completed_artifacts(self):
        value={'stop_reason':'end_turn','content':[{'type':'text','text':self.artifacts()}]}
        self.assertEqual(g.parse('anthropic',value,['a'])[0]['a'],'verified')

    def test_tool_calls_refusals_and_incomplete_responses_rejected(self):
        cases=[('openai',{'status':'completed','output':[{'type':'function_call'}]}),
               ('openai',{'status':'incomplete'}),
               ('openai',{'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]}),
               ('anthropic',{'stop_reason':'tool_use','content':[]})]
        for provider,value in cases:
            with self.subTest(provider=provider),self.assertRaises(ValueError):g.parse(provider,value,['a'])

    def test_missing_credentials_no_network_call(self):
        with patch.dict(os.environ,{},clear=True),patch.object(g.urllib.request,'build_opener') as opener:
            with self.assertRaisesRegex(ValueError,'OPENAI_API_KEY'):g.request('openai','explicit','prompt',10)
            opener.assert_not_called()

    def test_redirects_rejected(self):
        with self.assertRaisesRegex(ValueError,'redirects'):g.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_http_payload_has_no_tools_and_uses_fixed_endpoint(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'{"status":"completed"}'
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-key'}),patch.object(g.urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=Response();g._request('openai','explicit','prompt',10)
            request=opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url,g.PROVIDERS['openai'][0]);payload=json.loads(request.data)
        self.assertEqual(payload['tools'],[]);self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'],g.MAX_OUTPUT_TOKENS)

    def test_cli_steps_fail_closed_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'task.txt').write_text('task')
            plan={'schema_version':1,'id':'enforced-demo','steps':[{'id':'build','kind':'model','host':'codex','role':'fullstack-mvp-engineer','summary':'build','inputs':['task.txt'],'outputs':['a'],'allow_host_cli':True}]}
            (root/'workflow.json').write_text(json.dumps(plan));plan,fingerprint=w.read_plan(root,'workflow.json')
            with patch.object(h,'generate') as generate:report=w.run(root,plan,fingerprint,'image')
            self.assertEqual(report['status'],'failed');self.assertIn('disabled',report['blocker']);generate.assert_not_called()

    def test_untrusted_model_cannot_rewrite_trusted_runtime(self):
        import execution_policy as p
        with self.assertRaisesRegex(ValueError,'read-only'):
            p.destinations(w.LIBRARY,['scripts/workflow.py'])


if __name__=='__main__':unittest.main()
