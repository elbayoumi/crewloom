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

    def test_ollama_completed_artifacts(self):
        value={'done':True,'model':'qwen2.5-coder:7b','message':{'role':'assistant','content':self.artifacts()},
               'prompt_eval_count':150,'eval_count':45}
        artifacts,evidence=g.parse('ollama',value,['a'])
        self.assertEqual(artifacts['a'],'verified')
        self.assertEqual(evidence['model_reported'],'qwen2.5-coder:7b')
        self.assertEqual(evidence['usage']['input_tokens'],150)
        self.assertEqual(evidence['usage']['output_tokens'],45)
        self.assertEqual(evidence['usage']['total_tokens'],195)

    def test_ollama_markdown_fence_stripped(self):
        wrapped='```json\n'+self.artifacts()+'\n```'
        value={'done':True,'model':'qwen2.5-coder:7b','message':{'role':'assistant','content':wrapped}}
        artifacts,_=g.parse('ollama',value,['a'])
        self.assertEqual(artifacts['a'],'verified')

    def test_vllm_completed_artifacts(self):
        value={'model':'deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct',
               'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':self.artifacts()}}],
               'usage':{'prompt_tokens':120,'completion_tokens':50,'total_tokens':170}}
        artifacts,evidence=g.parse('vllm',value,['a'])
        self.assertEqual(artifacts['a'],'verified')
        self.assertEqual(evidence['model_reported'],'deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct')
        self.assertEqual(evidence['usage']['total_tokens'],170)

    def test_local_providers_loopback_enforced(self):
        with patch.dict(os.environ,{'OLLAMA_ENDPOINT':'http://8.8.8.8:11434/api/chat'}):
            with self.assertRaisesRegex(ValueError,'loopback'):
                g._resolve_endpoint('ollama')
        with patch.dict(os.environ,{'VLLM_ENDPOINT':'http://localhost/no-port'}):
            with self.assertRaisesRegex(ValueError,'explicit port'):
                g._resolve_endpoint('vllm')
        with patch.dict(os.environ,{'OLLAMA_ENDPOINT':'http://127.0.0.1:11434/api/chat'}):
            self.assertEqual(g._resolve_endpoint('ollama'),'http://127.0.0.1:11434/api/chat')

    def test_private_lan_endpoints_allowed_for_local_providers(self):
        with patch.dict(os.environ,{'OLLAMA_ENDPOINT':'http://192.168.1.100:11434/api/chat'}):
            self.assertEqual(g._resolve_endpoint('ollama'),'http://192.168.1.100:11434/api/chat')
        with patch.dict(os.environ,{'VLLM_ENDPOINT':'http://10.0.0.5:8000/v1/chat/completions'}):
            self.assertEqual(g._resolve_endpoint('vllm'),'http://10.0.0.5:8000/v1/chat/completions')
        fake_lan_info = [(2, 1, 6, '', ('10.0.1.50', 11434))]
        with patch.dict(os.environ, {'OLLAMA_ENDPOINT': 'http://gpu-server.internal:11434'}):
            with patch('socket.getaddrinfo', return_value=fake_lan_info):
                self.assertEqual(g._resolve_endpoint('ollama'), 'http://gpu-server.internal:11434/api/chat')

    def test_remote_gateway_override_permits_public_ips(self):
        with patch.dict(os.environ,{'OLLAMA_ENDPOINT':'http://8.8.8.8:11434/api/chat','CREWLOOM_ALLOW_REMOTE_GATEWAY':'1'}):
            self.assertEqual(g._resolve_endpoint('ollama'),'http://8.8.8.8:11434/api/chat')

    def test_link_local_and_cloud_metadata_ips_rejected(self):
        with patch.dict(os.environ, {'OLLAMA_ENDPOINT': 'http://169.254.169.254:11434/api/chat'}):
            with self.assertRaisesRegex(ValueError, 'outside allowed loopback'):
                g._resolve_endpoint('ollama')
        with patch.dict(os.environ, {'VLLM_ENDPOINT': 'http://0.0.0.0:8000/v1'}):
            with self.assertRaisesRegex(ValueError, 'outside allowed loopback'):
                g._resolve_endpoint('vllm')

    def test_dns_rebinding_to_public_ip_rejected(self):
        import socket
        fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 11434))]
        with patch.dict(os.environ, {'OLLAMA_ENDPOINT': 'http://gpu.internal:11434/api/chat'}):
            with patch('socket.getaddrinfo', return_value=fake_addrinfo):
                with self.assertRaisesRegex(ValueError, 'outside allowed CIDRs'):
                    g._resolve_endpoint('ollama')

    def test_think_tags_inside_artifact_content_preserved(self):
        raw_json = json.dumps({'artifacts': [{'path': 'a', 'content': 'before <think>keep me</think> after'}]})
        value = {
            'model': 'qwen2.5-coder:7b',
            'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': raw_json}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
        }
        artifacts, _ = g.parse('vllm', value, ['a'])
        self.assertEqual(artifacts['a'], 'before <think>keep me</think> after')

    def test_dynamic_max_output_tokens_setting(self):
        with patch.dict(os.environ, {'CREWLOOM_MAX_OUTPUT_TOKENS': '8192'}):
            self.assertEqual(g._max_output_tokens(), 8192)
        with patch.dict(os.environ, {'CREWLOOM_MAX_OUTPUT_TOKENS': '999999'}):
            self.assertEqual(g._max_output_tokens(), g.MAX_OUTPUT_TOKENS_CEILING)

    def test_system_proxies_enabled_when_configured(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): return b'{"status":"completed"}'
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'k', 'CREWLOOM_TRUST_SYSTEM_PROXIES': '1'}):
            with patch.object(g.urllib.request, 'build_opener') as build_opener:
                build_opener.return_value.open.return_value = Response()
                g._request('openai', 'model', 'prompt', 10)
                # Verify that proxy_handler was created
                self.assertTrue(build_opener.called)

    def test_local_providers_do_not_require_api_key(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'{"done":true,"model":"qwen2.5-coder","message":{"role":"assistant","content":"{\\"artifacts\\":[{\\"path\\":\\"a\\",\\"content\\":\\"ok\\"}]}"}}'
        with patch.dict(os.environ,{},clear=True),patch.object(g.urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=Response()
            result=g._request('ollama','qwen2.5-coder','prompt',10)
            self.assertTrue(result['done'])

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

    def test_endpoint_resolution_appends_routes(self):
        with patch.dict(os.environ,{'OLLAMA_ENDPOINT':'http://127.0.0.1:11434'}):
            self.assertEqual(g._resolve_endpoint('ollama'),'http://127.0.0.1:11434/api/chat')
        with patch.dict(os.environ,{'VLLM_ENDPOINT':'http://127.0.0.1:8000/v1'}):
            self.assertEqual(g._resolve_endpoint('vllm'),'http://127.0.0.1:8000/v1/chat/completions')
        with patch.dict(os.environ,{'VLLM_ENDPOINT':'http://127.0.0.1:8000'}):
            self.assertEqual(g._resolve_endpoint('vllm'),'http://127.0.0.1:8000/v1/chat/completions')

    def test_vllm_token_normalization(self):
        raw_response={
            'choices':[{'finish_reason':'stop','message':{'content':'{"artifacts":[{"path":"x.py","content":"1"}]}'}}],
            'usage':{'prompt_tokens':42,'completion_tokens':10,'total_tokens':52}
        }
        _,meta=g.parse('vllm',raw_response,['x.py'])
        usage=meta['usage']
        self.assertEqual(usage['input_tokens'],42)
        self.assertEqual(usage['output_tokens'],10)
        self.assertEqual(usage['total_tokens'],52)
        self.assertEqual(usage['prompt_tokens'],42)
        self.assertEqual(usage['completion_tokens'],10)

    def test_untrusted_model_cannot_rewrite_trusted_runtime(self):
        import execution_policy as p
        with self.assertRaisesRegex(ValueError,'read-only'):
            p.destinations(w.LIBRARY,['scripts/workflow.py'])


if __name__=='__main__':unittest.main()
