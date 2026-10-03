import json, hashlib
from pathlib import Path
c=json.loads(Path('crewloom-hook-pilot/context.json').read_text())
a=json.loads(Path('crewloom-hook-pilot/acceptance.json').read_text())
body=next(b for b in c['bodies'] if b['path']==a['seed'])
checks={
 'project_identity':c['scope']['project_id']==a['project_id'],
 'language':c['scope']['language']==a['language'],
 'seed_navigation':a['seed'] in c['navigation']['text'],
 'whole_source':body['text']==Path(a['seed']).read_text(),
 'body_fingerprint':body['sha256']==hashlib.sha256(Path(a['seed']).read_bytes()).hexdigest(),
 'required_symbols':all(s in body['text'] for s in a['required_symbols']),
 'direct_relative_imports':all(p in c['neighbours'] for p in a['required_neighbours']),
 'budget':len(Path('crewloom-hook-pilot/context.json').read_bytes())<=131072,
 'complete_rules':any(r['path'].endswith('context-guardian/SKILL.md') for r in c['rules']),
}
Path('crewloom-hook-pilot/result.json').write_text(json.dumps({'checks':checks,'passed':all(checks.values())}))
raise SystemExit(0 if all(checks.values()) else 1)
