"""Deterministic demonstration stages; no model calls or claimed AI review."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def write(name, value):
    path = Path(name); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage');stage=parser.parse_args().stage
    if stage == 'discover':
        requirements=Path('inputs/requirements.md').read_text()
        write('artifacts/acceptance.md',requirements+'\nAcceptance is enforced by tests/test_slug.py.\n')
    elif stage == 'architect':
        write('artifacts/architecture.md','# Architecture\n\nPure function in src/slug.py; standard-library Unicode normalization; no network, persistence or credentials.\n')
    elif stage == 'implement':
        Path('src').mkdir(exist_ok=True);shutil.copyfile('solution/slug.py','src/slug.py')
    elif stage == 'review':
        import ast
        ast.parse(Path('src/slug.py').read_text())
        write('artifacts/source-review.json',json.dumps({'syntax':'passed','scope':'Python parse only; no independent semantic review claim'}))
    elif stage == 'test':
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],capture_output=True,text=True)
        write('artifacts/test-results.json',json.dumps({'exit_code':result.returncode,'output':result.stdout+result.stderr}))
        return result.returncode
    elif stage == 'deliver':
        tests=json.loads(Path('artifacts/test-results.json').read_text())
        if tests['exit_code'] != 0: return 1
        write('artifacts/delivery.json',json.dumps({'feature':'Unicode slugify','source_sha256':hashlib.sha256(Path('src/slug.py').read_bytes()).hexdigest(),'tests':tests,'limits':['Supplied implementation fixture; no model-quality claim','Source review checks syntax only']}))
    else:
        parser.error('Unknown stage')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
