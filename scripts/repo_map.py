"""Project-local, bounded symbol maps; parsing cache keyed by content hashes."""
import argparse
import ast
import hashlib
import json
import os
import posixpath
from pathlib import Path
import re
import subprocess
import tempfile

EXTENSIONS={'.py','.js','.jsx','.ts','.tsx','.mjs','.cjs'}
EXCLUDED={'.git','.crewloom','.agents','.claude','node_modules','.next','dist','build','.venv','vendor','__pycache__'}
MAX_FILE=1024*1024
MAX_TOTAL=32*1024*1024
MAX_FILES=5000
VERSION=1


def structure(path,text):
    symbols=[];imports=[];parser='python-ast' if path.endswith('.py') else 'approximate-js-ts'
    if parser=='python-ast':
        try:tree=ast.parse(text)
        except SyntaxError:return {'symbols':[],'imports':[],'parser':'syntax-error'}
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                symbols.append({'name':node.name,'line':node.lineno,'kind':type(node).__name__})
            elif isinstance(node,ast.Import):imports.extend(a.name for a in node.names)
            elif isinstance(node,ast.ImportFrom):imports.append('.'*node.level+(node.module or ''))
    else:
        pattern=r'(?m)^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(function|class|interface|type|const|let)\s+([\w$]+)'
        for match in re.finditer(pattern,text):
            symbols.append({'name':match[2],'line':text.count('\n',0,match.start())+1,'kind':match[1]})
        imports=re.findall(r'''(?:from\s*|import\s*|require\(\s*)['"]([^'"\n]+)['"]''',text)
    return {'symbols':sorted(symbols,key=lambda x:x['line'])[:128],'imports':sorted(set(imports))[:64],'parser':parser}


def build(root):
    import workflow as w
    root=Path(root).resolve()
    if not root.is_dir():raise ValueError('Explicit existing project root required')
    cache=w.safe_path(root,'.crewloom/repo-map.json',internal=True)
    for candidate in (root/'.crewloom',root/'.crewloom/repo-map.json'):
        if candidate.is_symlink():raise ValueError('Map cache cannot use symlinks')
    prior={}
    if cache.exists():
        if cache.stat().st_size>8*MAX_FILE:raise ValueError('Map cache exceeds budget')
        value=json.loads(cache.read_text())
        if value.get('project_root')!=str(root):raise ValueError('Map cache belongs to another project')
        if value.get('version')==VERSION:prior=value.get('files',{})
    result=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=root,capture_output=True,timeout=15)
    if result.returncode:raise ValueError('Repository map requires a Git project; initialize Git explicitly')
    names=sorted(set(result.stdout.decode().split('\0'))- {''})
    files={};total=0;reused=0;parsed=0;skipped=0
    for name in names:
        parts=Path(name).parts
        if EXCLUDED.intersection(parts) or Path(name).suffix not in EXTENSIONS:continue
        path=w.safe_path(root,name)
        if any((root.joinpath(*parts[:i])).is_symlink() for i in range(1,len(parts)+1)):
            raise ValueError('Mapped paths cannot use symlinks')
        if not path.exists():continue
        if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('Map requires regular files without hardlinks')
        if path.stat().st_size>MAX_FILE:skipped+=1;continue
        if len(files)>=MAX_FILES or total+path.stat().st_size>MAX_TOTAL:raise ValueError('Repository map scan budget exceeded; split the project')
        raw=path.read_bytes();total+=len(raw);fingerprint=hashlib.sha256(raw).hexdigest()
        if prior.get(name,{}).get('sha256')==fingerprint:
            entry=prior[name];reused+=1
        else:
            try:text=raw.decode('utf-8')
            except UnicodeError:skipped+=1;continue
            entry=structure(name,text);entry['sha256']=fingerprint;parsed+=1
        files[name]=entry
    value={'version':VERSION,'project_root':str(root),'files':files}
    data=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
    if len(data)>8*MAX_FILE:raise ValueError('Map cache exceeds budget')
    cache.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache.parent,delete=False) as stream:
        temporary=Path(stream.name);stream.write(data)
    os.replace(temporary,cache)
    return value,{'files':len(files),'parsed':parsed,'reused':reused,'skipped':skipped,'scan_bytes':total}


def render(value,query,budget=8192,seeds=()):
    if type(budget) is not int or not 1024<=budget<=65536:raise ValueError('Map budget must be 1024..65536 bytes')
    words=set(re.findall(r'\w{3,}',query.casefold()));files=value['files']
    # Direct import relationships provide a lightweight dependency hint, not a call graph.
    neighbours=set()
    for seed in seeds:
        for module in files.get(seed,{}).get('imports',[]):
            base=posixpath.normpath((Path(seed).parent/module).as_posix()) if module.startswith('.') and not seed.endswith('.py') else module.replace('.','/').lstrip('/')
            for candidate in files:
                if candidate.rsplit('.',1)[0]==base:neighbours.add(candidate)
    def score(name):
        text=name+' '+ ' '.join(s['name'] for s in files[name]['symbols'])
        return (name in seeds,name in neighbours,len(words & set(re.findall(r'\w{3,}',text.casefold()))))
    result='Repository navigation map; definitions are hints, not complete source or executed evidence.\n'
    included=0
    for name in sorted(files,key=lambda n:(tuple(-int(x) for x in score(n)),n)):
        entry=files[name]
        block=name+' ['+entry['parser']+']\n'+''.join('  '+s['kind']+' '+s['name']+' :'+str(s['line'])+'\n' for s in entry['symbols'])
        if len((result+block).encode())<=budget:result+=block;included+=1
    return result,{'included_files':included,'omitted_files':len(files)-included,'map_bytes':len(result.encode())}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True);parser.add_argument('--query',default='')
    parser.add_argument('--budget',type=int,default=8192)
    args=parser.parse_args(argv)
    try:
        value,stats=build(Path(args.project));text,selection=render(value,args.query,args.budget)
        print(json.dumps({'map':text,'stats':dict(stats,**selection)},ensure_ascii=False));return 0
    except (ValueError,OSError,subprocess.SubprocessError) as exc:print(json.dumps({'error':str(exc)}));return 2


if __name__=='__main__':raise SystemExit(main())
