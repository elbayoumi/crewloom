"""Collect model artifacts and score them without provider/treatment labels."""
import argparse
import json
from pathlib import Path
import random
import tempfile
import time

import evaluate_feature as grader
import model_host as host
import workflow as w

TASK='''Implement src/slug.py with a Python standard-library function slugify(value).
Require a string or raise TypeError. Normalize with Unicode NFKC and casefold.
Keep Unicode letters and decimal digits (including Arabic). Treat each run of
other characters as one hyphen. Trim leading and trailing hyphens. Empty or
punctuation-only input returns an empty string. Return only the artifact; no tools.
'''


def trial_order(hosts, repeats, seed):
    if not hosts or len(set(hosts))!=len(hosts) or any(item not in host.HOSTS for item in hosts):
        raise ValueError('Choose unique codex/claude hosts')
    if type(repeats) is not int or not 1<=repeats<=20:raise ValueError('Repeats must be from 1 to 20')
    trials=[{'host':name,'condition':condition,'repeat':repeat} for name in hosts
            for condition in ('without-role','with-role') for repeat in range(1,repeats+1)]
    random.Random(seed).shuffle(trials)
    return trials


def collect(destination, hosts, repeats=5, seed=20261001, image=w.DEFAULT_IMAGE, models=None, timeout=180):
    destination=destination.resolve()
    if destination.exists():raise ValueError('Use a fresh output directory; existing evidence is never overwritten')
    if type(timeout) is not int or not 1<=timeout<=3600:raise ValueError('Timeout must be from 1 to 3600')
    # Freeze the scorer and prompt hashes before the first provider call.
    image_id=w.inspect_image(image)
    trials=trial_order(hosts,repeats,seed)
    role=w.LIBRARY/'.agents/skills/fullstack-mvp-engineer'
    role_text=(role/'SKILL.md').read_text()+'\n'+(role/'references/PLAYBOOK.en.md').read_text()
    prompts={'without-role':TASK,'with-role':role_text+'\n\nTask:\n'+TASK}
    destination.mkdir(parents=True)
    frozen={'benchmark':'unicode-slug-v1','seed':seed,'repeats_per_condition':repeats,
            'image_id':image_id,'scorer_sha256':w.digest(Path(grader.__file__).read_bytes()),
            'cases_sha256':w.digest(json.dumps(grader.CASES,ensure_ascii=False).encode()),
            'prompt_sha256':{key:w.digest(value.encode()) for key,value in prompts.items()},
            'models_requested':models or {},'trial_order':trials,
            'limits':['Single public pure-function task; acceptance cases are public',
                      'Deterministic grader separate from producing host; no independent human coordinator',
                      'Role treatment includes extra prompt length; default host models may differ',
                      'Artifact acceptance measures this contract only, not general agency performance']}
    (destination/'protocol.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2))
    (destination/'task.md').write_text(TASK)
    for condition,prompt in prompts.items():(destination/(condition+'.txt')).write_text(prompt)
    results=[];failures={};mapping=[]
    for index,trial in enumerate(trials,1):
        ident='submission-'+str(index).zfill(3)
        if failures.get(trial['host'],0)>=2:
            results.append({'submission':ident,'status':'blocked','reason':'Two host failures; remaining calls skipped'})
            mapping.append({'submission':ident,**trial});continue
        started=time.monotonic()
        try:
            artifacts,evidence=host.generate(trial['host'],prompts[trial['condition']],['src/slug.py'],timeout,(models or {}).get(trial['host']))
            with tempfile.TemporaryDirectory(prefix='crewloom-submission-') as t:
                project=Path(t).resolve();(project/'src').mkdir();(project/'src/slug.py').write_text(artifacts['src/slug.py'])
                # Scorer sees source + image only, never this trial's host/condition.
                report=grader.evaluate(project,image,1)
            submission=destination/ident;submission.mkdir();(submission/'slug.py').write_text(artifacts['src/slug.py'])
            (submission/'score.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            (submission/'generation.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
            results.append({'submission':ident,'status':'scored','source_sha256':report['source_sha256'],
                            'pass_rate':report['mean_pass_rate'],'duration_ms':round((time.monotonic()-started)*1000)})
        except (ValueError,OSError) as exc:
            failures[trial['host']]=failures.get(trial['host'],0)+1
            results.append({'submission':ident,'status':'failed','error':str(exc)})
        mapping.append({'submission':ident,**trial})
        (destination/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        (destination/'mapping.json').write_text(json.dumps(mapping,indent=2))
    (destination/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    (destination/'mapping.json').write_text(json.dumps(mapping,indent=2))
    report={'protocol':frozen,'results':results,'groups':[]}
    for name in hosts:
        for condition in ('without-role','with-role'):
            ids={m['submission'] for m in mapping if m['host']==name and m['condition']==condition}
            values=[item for item in results if item['submission'] in ids]
            scored=[item['pass_rate'] for item in values if item['status']=='scored']
            report['groups'].append({'host':name,'condition':condition,'requested':repeats,'scored':len(scored),
                                    'mean_pass_rate':sum(scored)/len(scored) if scored else None,
                                    'failed_or_blocked':len(values)-len(scored)})
    report['cross_host_complete']=all(item['scored']==repeats for item in report['groups']) and len(hosts)>1
    (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--host',choices=host.HOSTS,action='append',required=True)
    parser.add_argument('--repeats',type=int,default=5);parser.add_argument('--seed',type=int,default=20261001)
    parser.add_argument('--image',default=w.DEFAULT_IMAGE);parser.add_argument('--timeout',type=int,default=180)
    parser.add_argument('--codex-model');parser.add_argument('--claude-model')
    args=parser.parse_args(argv)
    try:
        report=collect(Path(args.output),args.host,args.repeats,args.seed,args.image,
                       {key:value for key,value in (('codex',args.codex_model),('claude',args.claude_model)) if value},args.timeout)
        print(json.dumps({'groups':report['groups'],'cross_host_complete':report['cross_host_complete']},indent=2))
        return 0 if all(group['scored']==args.repeats for group in report['groups']) else 2
    except (ValueError,OSError) as exc:
        print(json.dumps({'error':str(exc)}));return 2


if __name__=='__main__':raise SystemExit(main())
