"""Independent tool-free transport and provider usage semantics, no provider calls."""
import copy,json,math,tempfile,unittest
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
import model_host as h
ARTIFACT={'artifacts':[{'path':'src/result.py','content':'VALUE = 1\n'}]}
TOKENS={'total':151,'input':100,'output':11,'reasoning':3,'cache':{'read':35,'write':2}}
def stream(*events):return '\n'.join(json.dumps(e) for e in events)
def text(value=ARTIFACT):return {'type':'text','part':{'text':json.dumps(value)}}
def finish(tokens=TOKENS,cost=0,reason='stop'):
 p={'reason':reason}
 if tokens is not None:p['tokens']=tokens
 if cost is not None:p['cost']=cost
 return {'type':'step_finish','part':p}
class TransportAcceptance(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  (self.root/'response.json').write_text(json.dumps(ARTIFACT))
 def test_opencode_actual_step_finish_schema_and_free_cost_are_decoded(self):
  value,usage,cost=h.parse_response('opencode',stream(text(),finish()),self.root)
  self.assertEqual(h.validate_artifacts(value,['src/result.py']),{'src/result.py':'VALUE = 1\n'})
  self.assertEqual(cost,0)
  normalized=h.usage_metrics('opencode',usage)
  self.assertEqual({k:normalized[k] for k in ('input_tokens','uncached_input_tokens','cached_input_tokens','cache_write_tokens','output_tokens','reasoning_tokens','total_tokens')}, {'input_tokens':137,'uncached_input_tokens':100,'cached_input_tokens':35,'cache_write_tokens':2,'output_tokens':11,'reasoning_tokens':3,'total_tokens':151})
 def test_tool_event_cannot_be_hidden_behind_a_valid_final_response(self):
  with self.assertRaises(ValueError):h.parse_response('opencode',stream({'type':'tool_use','part':{'tool':'bash'}},text(),finish()),self.root)
 def test_incomplete_or_failed_opencode_generation_is_refused(self):
  for raw in (stream(text()),stream(text(),finish(reason='length')),stream(text(),finish(),{'type':'error','error':{'message':'failed'}})):
   with self.subTest(raw=raw),self.assertRaises(ValueError):h.parse_response('opencode',raw,self.root)
 def test_duplicate_artifacts_are_refused(self):
  value={'artifacts':[ARTIFACT['artifacts'][0],ARTIFACT['artifacts'][0]]}
  with self.assertRaises(ValueError):h.validate_artifacts(value,['src/result.py'])
 def test_malformed_or_multiple_structured_responses_are_refused(self):
  for raw in (stream(text(),finish())+'\nnot-json',stream(text(),text(),finish())):
   with self.subTest(raw=raw),self.assertRaises(ValueError):h.parse_response('opencode',raw,self.root)
 def test_missing_usage_and_cost_are_unknown(self):
  value,usage,cost=h.parse_response('opencode',stream(text(),finish(tokens=None,cost=None)),self.root)
  self.assertEqual(value,ARTIFACT);self.assertIsNone(cost)
  metrics=h.usage_metrics('opencode',usage)
  for key in ('input_tokens','cached_input_tokens','output_tokens','reasoning_tokens','total_tokens'):self.assertIsNone(metrics[key])
 def test_multiple_observed_opencode_model_steps_are_aggregated(self):
  value,usage,cost=h.parse_response('opencode',stream({'type':'text','part':{'text':'Preparing result'}},finish(),text(),finish()),self.root)
  self.assertEqual(value,ARTIFACT);self.assertEqual(cost,0)
  metrics=h.usage_metrics('opencode',usage)
  self.assertEqual(metrics['input_tokens'],274);self.assertEqual(metrics['total_tokens'],302)
 def test_codex_cached_input_is_a_subset_not_added_to_input(self):
  metrics=h.usage_metrics('codex',{'input_tokens':100,'cached_input_tokens':40,'output_tokens':11})
  self.assertEqual(metrics['input_tokens'],100);self.assertEqual(metrics['uncached_input_tokens'],60);self.assertEqual(metrics['cached_input_tokens'],40);self.assertEqual(metrics['output_tokens'],11)
 def test_invalid_token_values_are_refused(self):
  for key,bad in (('input_tokens',-1),('input_tokens',True),('output_tokens',1.5),('cached_input_tokens',math.nan)):
   with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):h.usage_metrics('codex',{'input_tokens':100,'cached_input_tokens':40,'output_tokens':11, key:bad})
 def test_codex_completion_and_valid_artifacts_keep_actual_usage(self):
  value,usage,cost=h.parse_response('codex',stream({'type':'turn.completed','usage':{'input_tokens':100,'cached_input_tokens':40,'output_tokens':11}}),self.root)
  self.assertEqual(value,ARTIFACT);self.assertIsNone(cost);self.assertEqual(h.usage_metrics('codex',usage)['uncached_input_tokens'],60)
 def test_codex_real_tool_event_refuses_even_a_valid_response_file(self):
  raw=stream({'type':'item.completed','item':{'type':'command_execution','command':'echo unsafe'}},{'type':'turn.completed','usage':{}})
  with self.assertRaises(ValueError):h.parse_response('codex',raw,self.root)
 def test_codex_response_file_without_completion_is_refused(self):
  with self.assertRaises(ValueError):h.parse_response('codex','',self.root)
 def test_missing_cached_usage_is_not_invented(self):
  metrics=h.usage_metrics('codex',{'input_tokens':100,'output_tokens':11})
  self.assertEqual(metrics['input_tokens'],100);self.assertIsNone(metrics['cached_input_tokens']);self.assertIsNone(metrics['uncached_input_tokens'])
if __name__=='__main__':unittest.main()
