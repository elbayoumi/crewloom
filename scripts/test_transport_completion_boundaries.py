"""Independent regressions for partial provider usage and unfinished final model steps."""
import tempfile,unittest
from pathlib import Path
import model_host as h
import test_transport_acceptance_boundaries as fixtures
class CompletionBoundaries(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
 def test_missing_cost_on_one_observed_step_makes_aggregate_cost_unknown(self):
  raw=fixtures.stream({'type':'text','part':{'text':'Preparing result'}},fixtures.finish(cost=None),fixtures.text(),fixtures.finish())
  _,_,cost=h.parse_response('opencode',raw,self.root)
  self.assertIsNone(cost,'A known zero from one step cannot price another step whose cost is absent')
 def test_missing_usage_on_one_step_cannot_be_silently_dropped_from_totals(self):
  raw=fixtures.stream({'type':'text','part':{'text':'Preparing result'}},fixtures.finish(tokens=None),fixtures.text(),fixtures.finish())
  _,usage,_=h.parse_response('opencode',raw,self.root)
  metrics=h.usage_metrics('opencode',usage)
  for key in ('input_tokens','output_tokens','cached_input_tokens','total_tokens'):
   self.assertIsNone(metrics[key],key+' aggregated an incomplete set of observed model steps')
 def test_previous_step_completion_cannot_verify_a_new_unfinished_structured_response(self):
  raw=fixtures.stream({'type':'step_start','part':{}},fixtures.finish(),{'type':'step_start','part':{}},fixtures.text())
  with self.assertRaises(ValueError):h.parse_response('opencode',raw,self.root)
if __name__=='__main__':unittest.main()
