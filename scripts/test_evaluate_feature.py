import unittest
import evaluate_feature as e


class ObjectiveGraderTests(unittest.TestCase):
    def test_correct_results_score_all_cases(self):
        actual={ident:expected for ident,_,expected in e.CASES}
        self.assertTrue(all(e.score(actual).values()))

    def test_omitted_and_wrong_results_fail(self):
        self.assertFalse(any(e.score({}).values()))
        actual={ident:expected for ident,_,expected in e.CASES};actual['arabic-spacing']=''
        self.assertFalse(e.score(actual)['arabic-spacing'])
        self.assertEqual(sum(e.score(actual).values()),len(e.CASES)-1)

    def test_non_object_results_rejected(self):
        with self.assertRaises(ValueError):e.score([])

    def test_probe_does_not_contain_held_out_expected_answers(self):
        self.assertNotIn('hello-world',e.PROBE)
        self.assertNotIn('مرحبا-بالعالم',e.PROBE)

    def test_public_cli_forwards_evaluation_flags(self):
        import subprocess,sys,json,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('crewloom.py')),'evaluate','--project',str(Path(folder)/'missing'),'--repeats','3'],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertNotIn('unrecognized arguments',result.stderr)
            self.assertIn('error',json.loads(result.stdout))
