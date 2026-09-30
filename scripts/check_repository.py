#!/usr/bin/env python3
"""Validate the exact public checkout and its core regression suites."""
import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

from crewloom import load_validator

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('skill-forge-recruiter', 'context-guardian')


def inspect(root):
    errors = []
    files = [p for p in root.rglob('*') if '.git' not in p.relative_to(root).parts
             and '__pycache__' not in p.relative_to(root).parts and p.is_file()]
    for path in files:
        if path.is_symlink():
            errors.append(f'Symlink excluded from distribution: {path.relative_to(root)}')
            continue
        if path.suffix == '.py':
            try:
                ast.parse(path.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeError) as exc:
                errors.append(f'Invalid Python: {path.relative_to(root)}: {exc}')
        if path.suffix != '.md':
            continue
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'```.*?```', '', text, flags=re.S)
        text = re.sub(r'`[^`]*`', '', text)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if re.match(r'(?:[a-zA-Z][\w+.-]*:|#)', target):
                continue
            local = unquote(target.split('#', 1)[0])
            resolved = (path.parent / local).resolve()
            if root.resolve() not in (resolved, *resolved.parents) or not resolved.exists():
                errors.append(f'Broken or escaping link: {path.relative_to(root)} -> {target}')
    if not (root / 'LICENSE').is_file():
        errors.append('Missing LICENSE')
    if not list((root / '.agents' / 'skills').glob('*/SKILL.md')):
        errors.append('No skills found')
    validator = load_validator()
    validator.REPO = root
    for path in (root / '.agents' / 'skills').glob('*/SKILL.md'):
        errors.extend(f'{path.parent.name}: {error}' for error in validator.check(path.parent.name))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true')
    args = parser.parse_args()
    errors = inspect(ROOT)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    if not args.skip_tests:
        directories = [ROOT / '.agents' / 'skills' / name / 'scripts' for name in SUITES]
        directories.append(ROOT / 'scripts')
        for directory in directories:
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
                                     str(directory), '-p', 'test_*.py'], timeout=60, check=False)
            if result.returncode:
                return result.returncode
    print('PASS: public repository structure, Python syntax, links, and requested regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
