"""Objective held-out acceptance scoring for the Unicode slug feature benchmark."""
import argparse
import json
from pathlib import Path
import tempfile

import workflow as w

# Expected answers stay in the host grader, outside the candidate container.
CASES = [
    ('english-punctuation', 'Hello, WORLD!', 'hello-world'),
    ('arabic-spacing', 'مرحبا بالعالم', 'مرحبا-بالعالم'),
    ('compatibility-forms', 'Ｆｏｏ １２３', 'foo-123'),
    ('case-folding', 'Straße', 'strasse'),
    ('repeated-separators', 'one___two--three', 'one-two-three'),
    ('empty-input', '', ''),
    ('punctuation-only', ' --- !!! ', ''),
    ('arabic-digits', 'طلب ١٢٣', 'طلب-١٢٣'),
    ('invalid-type', None, {'error': 'TypeError'}),
]
PROBE = '''import importlib.util,json,pathlib
spec=importlib.util.spec_from_file_location('submission','src/slug.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
actual={}
for case in json.loads(pathlib.Path('requests.json').read_text()):
 try:actual[case['id']]=module.slugify(case['input'])
 except Exception as exc:actual[case['id']]={'error':type(exc).__name__}
pathlib.Path('actual.json').write_text(json.dumps(actual,ensure_ascii=False))
'''


def score(actual):
    if not isinstance(actual, dict):
        raise ValueError('Candidate results must be an object')
    return {ident: actual.get(ident) == expected for ident, _, expected in CASES}


def evaluate(project, image=w.DEFAULT_IMAGE, repeats=3):
    project=project.resolve(strict=True)
    source=w.safe_path(project,'src/slug.py')
    if not source.is_file():raise ValueError('Benchmark submission needs src/slug.py')
    source_bytes=source.read_bytes();image_id=w.inspect_image(image)
    runs=[]
    for _ in range(repeats):
        with tempfile.TemporaryDirectory(prefix='crewloom-grade-') as folder:
            stage=Path(folder).resolve();(stage/'src').mkdir()
            (stage/'src/slug.py').write_bytes(source_bytes)
            (stage/'requests.json').write_text(json.dumps([{'id':ident,'input':value} for ident,value,_ in CASES],ensure_ascii=False))
            (stage/'probe.py').write_text(PROBE)
            result=w.docker_execute(stage,['python3','probe.py'],image_id,30)
            if result['exit_code']:
                runs.append({'passed':0,'total':len(CASES),'execution_error':result['output'],'duration_ms':result['duration_ms']})
                continue
            actual=json.loads((stage/'actual.json').read_text());checks=score(actual)
            runs.append({'passed':sum(checks.values()),'total':len(CASES),'cases':checks,'duration_ms':result['duration_ms']})
    return {'benchmark':'unicode-slug-v1','source_sha256':w.digest(source_bytes),'image_id':image_id,'runs':runs,
            'mean_pass_rate':sum(run['passed']/run['total'] for run in runs)/len(runs),
            'limits':['Single pure-function benchmark','No model condition is provided to the scorer','Not a cross-provider or independent-human-review result']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True);parser.add_argument('--image',default=w.DEFAULT_IMAGE)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args(argv)
    if not 1<=args.repeats<=20:parser.error('Repeats must be from 1 to 20')
    try:
        report=evaluate(Path(args.project),args.image,args.repeats)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report['mean_pass_rate']==1 else 1
    except (ValueError,OSError) as exc:
        print(json.dumps({'error':str(exc)}));return 2


if __name__=='__main__':raise SystemExit(main())
