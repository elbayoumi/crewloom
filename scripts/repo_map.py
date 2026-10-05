"""Project-local, bounded symbol maps; versioned generations, SHA-verified reuse.

The map is a navigation index, not a source of truth. Every refresh re-reads and
re-hashes candidate bytes, so reuse saves parsing and transmitted context only.
Python extraction uses the standard AST; JavaScript and TypeScript use real syntax
trees when the optional `crewloom[syntax]` extra is installed and a labelled
approximate extractor otherwise. Module specifiers this index cannot follow are
reported rather than hidden.
"""
import argparse
import ast
import hashlib
import json
import os
import posixpath
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import js_syntax

EXTENSIONS={'.py','.js','.jsx','.ts','.tsx','.mjs','.cjs'}
JS_EXTENSIONS=('.ts','.tsx','.js','.jsx','.mjs','.cjs')
EXCLUDED={'.git','.crewloom','.agents','.claude','node_modules','.next','dist','build','.venv','vendor','__pycache__'}
# Standard-library imports are external dependencies, not unresolved project edges. Counting
# them as unresolved would mark every ordinary Python file as an incomplete graph.
# `sys.stdlib_module_names` exists from 3.10; the explicit list keeps Python 3.9 identical.
STDLIB=frozenset(getattr(sys,'stdlib_module_names',()) or ())|frozenset((
    'abc','argparse','array','ast','asyncio','base64','binascii','bisect','calendar','collections',
    'concurrent','configparser','contextlib','copy','csv','ctypes','dataclasses','datetime','decimal',
    'difflib','dis','email','enum','errno','faulthandler','fcntl','filecmp','fnmatch','fractions',
    'ftplib','functools','gc','getpass','gettext','glob','gzip','hashlib','heapq','hmac','html',
    'http','importlib','inspect','io','ipaddress','itertools','json','keyword','linecache','locale',
    'logging','lzma','mimetypes','multiprocessing','operator','os','pathlib','pickle','pkgutil',
    'platform','plistlib','pprint','queue','random','re','secrets','select','shlex','shutil','signal',
    'site','smtplib','socket','sqlite3','ssl','stat','statistics','string','struct','subprocess',
    'sys','sysconfig','tarfile','tempfile','textwrap','threading','time','timeit','token','tokenize',
    'traceback','types','typing','unicodedata','unittest','urllib','uuid','venv','warnings','wave',
    'weakref','webbrowser','xml','xmlrpc','zipfile','zlib'))
MAX_FILE=1024*1024
MAX_TOTAL=32*1024*1024
MAX_FILES=5000
MAX_SEEDS=64
MAX_SYMBOLS=128
MAX_IMPORTS=64
MAX_SEED_SYMBOLS=12
CACHE_RELATIVE='.crewloom/index/map.json'
GENERATION_VERSION=2
SCHEMA_VERSION=2
# Cache keys name the exact extractor: a grammar upgrade changes the `ts-ast` revision, and
# the approximate fallback keeps its own version so changing either one re-parses.
PARSER_VERSIONS={'python-ast':2,'approximate-js-ts':4,'ts-ast':js_syntax.revision(),'syntax-error':2}
JS_GRAMMAR=js_syntax.available()
NOT_A_GIT_PROJECT='Repository map requires a Git project; initialize Git explicitly'
NO_GIT_WORK_TREE='Repository map requires a Git project with a work tree at this root; bare repositories are unsupported'
# Git reads its repository location, index and configuration from the environment as well as from
# the working directory. GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, GIT_COMMON_DIR,
# GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES, GIT_CEILING_DIRECTORIES, GIT_CONFIG,
# GIT_CONFIG_PARAMETERS and the GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n block all
# redirect a child process at another repository, work tree, index or configuration, and a commit
# hook exports exactly those variables. Every Git child therefore starts from an environment
# without them: only author and committer identities survive, and PATH, locale and TZ are kept.
GIT_IDENTITY_PREFIXES=('GIT_AUTHOR_','GIT_COMMITTER_')
HEADER=('Repository navigation map; definitions are hints, not complete source or executed evidence.\n'
        'Symbol lists are truncated and the dependency graph is partial; read the real file.\n')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git_environment(base=None):
    """The caller's environment minus inherited Git repository, index and configuration overrides."""
    source=os.environ if base is None else base
    return {key:value for key,value in source.items()
            if not key.startswith('GIT_') or key.startswith(GIT_IDENTITY_PREFIXES)}


def identity(root):
    """Reuse the project binding when present; a missing binding is not project identity."""
    binding=Path(root)/'.crewloom'/'binding.json'
    if not binding.is_file() or binding.is_symlink():return {'project_id':None,'checkout_id':None}
    try:
        value=json.loads(binding.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return {'project_id':None,'checkout_id':None}
    if not isinstance(value,dict) or value.get('project_root')!=str(root):return {'project_id':None,'checkout_id':None}
    return {'project_id':value.get('project_id'),'checkout_id':value.get('checkout_id')}


def git(root,argv,timeout=20):
    result=subprocess.run(['git',*argv],cwd=root,capture_output=True,timeout=timeout,env=git_environment())
    if result.returncode:raise ValueError(NOT_A_GIT_PROJECT)
    return result.stdout


def git_optional(root,argv,timeout=20):
    """An unborn branch or detached HEAD is a legitimate repository state, not a failure."""
    try:result=subprocess.run(['git',*argv],cwd=root,capture_output=True,timeout=timeout,
                              env=git_environment())
    except (OSError,subprocess.SubprocessError):return ''
    return '' if result.returncode else result.stdout.decode('utf-8','replace').strip()


def git_dir_for(root):
    """The repository directory this checkout declares for itself, read from its own `.git` marker."""
    marker=Path(root)/'.git'
    if marker.is_dir():return marker.resolve()
    if marker.is_file():
        text=marker.read_text(encoding='utf-8',errors='replace').strip()
        if not text.lower().startswith('gitdir:'):
            raise ValueError('Malformed .git marker: '+str(marker))
        target=Path(text.split(':',1)[1].strip())
        return (target if target.is_absolute() else marker.parent/target).resolve()
    return None


def require_git_root(root):
    """Bind the selected root to the Git checkout that owns it, never to an inherited one.

    Discovery runs with a cleared Git environment and must reproduce the repository directory this
    root's own `.git` marker names, with its work tree at this root. An environment redirect, a
    subdirectory of another checkout, a bare repository and a plain directory are all refused
    instead of being mapped as if they were this project.
    """
    root=Path(root).resolve()
    if not root.is_dir():raise ValueError('Explicit existing project root required')
    declared=git_dir_for(root)
    if declared is None:raise ValueError(NOT_A_GIT_PROJECT)
    discovered=git_optional(root,['rev-parse','--absolute-git-dir'])
    if not discovered:raise ValueError(NOT_A_GIT_PROJECT)
    if Path(discovered).resolve()!=declared:
        raise ValueError('Git repository discovered for this root belongs to another checkout: '+discovered)
    top=git_optional(root,['rev-parse','--show-toplevel'])
    if not top:raise ValueError(NO_GIT_WORK_TREE)
    if Path(top).resolve()!=root:
        raise ValueError('Git work tree for this root is a different directory: '+top)
    return {'git_dir':str(Path(discovered).resolve()),'work_tree':str(Path(top).resolve())}


def git_state(root):
    """Nominate changed, untracked, deleted and renamed paths from Git, without trusting freshness."""
    root=Path(root).resolve()
    require_git_root(root)
    head=git_optional(root,['rev-parse','--verify','--quiet','HEAD'])
    branch=git_optional(root,['symbolic-ref','--quiet','--short','HEAD']) or git_optional(root,['rev-parse','--abbrev-ref','HEAD'])
    tracked=set(filter(None,git(root,['ls-files','-z','--cached','--others','--exclude-standard']).decode('utf-8','replace').split('\0')))
    status=subprocess.run(['git','status','--porcelain=v1','-z','--untracked-files=all'],cwd=root,
                          capture_output=True,timeout=20,env=git_environment())
    if status.returncode:raise ValueError('Git status failed; repository map cannot nominate changed files')
    fields=[field for field in status.stdout.decode('utf-8','replace').split('\0') if field]
    changed=set();deleted=set();renamed={};untracked=set()
    index=0
    while index<len(fields):
        entry=fields[index];index+=1
        code,_,name=entry[:2],entry[2:3],entry[3:]
        if 'R' in code[:2]:
            old=fields[index] if index<len(fields) else ''
            index+=1
            renamed[name]=old;changed.add(name);deleted.add(old)
        if 'D' in code[:2]:deleted.add(name)
        elif code[:2]=='??':untracked.add(name)
        else:changed.add(name)
    return {'head':head,'branch':branch,'names':sorted(tracked),'changed':changed,'deleted':deleted,
            'renamed':renamed,'untracked':untracked}


def python_candidates(seed,imports):
    """Resolve Python import specifiers against a package layout the map actually indexed."""
    parent=Path(seed).parent
    found=[]
    for spec in imports:
        level=spec['relative']
        if level:
            base=parent
            for _ in range(level-1):
                if base.parent==base:break
                base=base.parent
            stem=base/Path(*spec['module'].split('.')) if spec['module'] else base
        elif spec['module']:
            stem=Path(*spec['module'].split('.'))
        else:
            for name in spec['names']:
                if name!='*':found.append((Path(*name.split('.')).with_suffix('.py')).as_posix())
            continue
        found.append(stem.with_suffix('.py').as_posix())
        found.append((stem/'__init__.py').as_posix())
        for name in spec['names']:
            if name!='*':found.append((stem/Path(*name.split('.'))).as_posix()+'.py')
    return found


def js_candidates(seed,spec):
    """Relative JS/TS specifier candidates, kept for the approximate fallback path."""
    if not spec.startswith('.'):return []
    base=posixpath.normpath(posixpath.join(posixpath.dirname(seed),spec))
    return [base+extension for extension in JS_EXTENSIONS]+[posixpath.join(base,'index'+extension) for extension in JS_EXTENSIONS]


def structure(name,text):
    """Extract bounded navigation facts; unsupported syntax stays visible as incomplete."""
    symbols=[];imports=[];notes=[];complete=True
    if name.endswith('.py'):
        parser='python-ast'
        try:tree=ast.parse(text)
        except SyntaxError:
            return {'symbols':[],'imports':[],'parser':'syntax-error','symbols_truncated':0,'imports_truncated':0,
                    'notes':['python-syntax-error-not-indexed'],'complete':False}
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                symbols.append({'name':node.name,'line':node.lineno,'end':getattr(node,'end_lineno',None) or node.lineno,'kind':type(node).__name__})
            elif isinstance(node,ast.Import):
                imports.append({'module':'','relative':0,'names':[alias.name for alias in node.names],'raw':'import '+', '.join(alias.name for alias in node.names)})
            elif isinstance(node,ast.ImportFrom):
                module=node.module or ''
                imports.append({'module':module,'relative':node.level,'names':[alias.name for alias in node.names],
                                'raw':'from '+'.'*node.level+module+' import '+', '.join(alias.name for alias in node.names)})
    elif JS_GRAMMAR and Path(name).suffix in js_syntax.GRAMMARS:
        # The real syntax tree, so declarations inside comments, strings and template
        # literals are not symbols and nested definitions are found where they are.
        parser='ts-ast'
        found=js_syntax.extract(name,text)
        symbols=found['symbols'];imports=found['imports'];notes=found['notes']
        # A syntax error, a parse-budget stop or an unfollowable module load means this file's
        # graph is a subset of the file. Carrying that through is what keeps a partial parse
        # out of the generation's `graph_complete` claim.
        complete=bool(found['complete'])
    else:
        parser='approximate-js-ts'
        pattern=r'(?m)^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(function|class|interface|type|const|let)\s+([\w$]+)'
        for match in re.finditer(pattern,text):
            symbols.append({'name':match[2],'line':text.count('\n',0,match.start())+1,'end':None,'kind':match[1]})
        imports=[{'module':spec,'relative':0,'names':[],'raw':spec}
                 for spec in re.findall(r'''(?:from\s*|import\s*|require\(\s*|import\(\s*)['"]([^'"\n]+)['"]''',text)]
        notes.append('js-ts-symbols-approximate-no-tree-sitter')
    symbols.sort(key=lambda item:(item['line'],item['name']))
    truncated=max(0,len(symbols)-MAX_SYMBOLS);symbols=symbols[:MAX_SYMBOLS]
    imports.sort(key=lambda item:item['raw'])
    imports_truncated=max(0,len(imports)-MAX_IMPORTS);imports=imports[:MAX_IMPORTS]
    return {'symbols':symbols,'imports':imports,'parser':parser,'symbols_truncated':truncated,
            'imports_truncated':imports_truncated,'notes':notes,'complete':complete}


def _external_python(spec):
    """True when an absolute specifier names only standard-library modules."""
    tops=[part.split('.')[0] for part in ([spec['module']] if spec['module'] else spec['names'])]
    return bool(tops) and all(top in STDLIB for top in tops)


def link(name,entry,files,resolver=None):
    """Attach resolved neighbours and the specifiers this index cannot follow.

    A specifier that names a package outside the project is recorded as external as well as
    unresolved: it is not a broken edge, and this index still cannot link it. Alias, dynamic
    and workspace-package outcomes are recorded as notes so a reader never has to guess why
    an edge is or is not present.
    """
    neighbours=set();unresolved=set();external=set();notes=set()
    if entry['parser']=='python-ast':
        for spec in entry['imports']:
            candidates=[candidate for candidate in python_candidates(name,[spec])
                        if candidate in files and candidate!=name]
            if candidates:neighbours.update(candidates)
            elif not spec['relative'] and _external_python(spec):continue
            else:unresolved.add(spec['raw'])
    else:
        for spec in entry['imports']:
            if resolver is None:
                candidates=[candidate for candidate in js_candidates(name,spec['module'])
                            if candidate in files and candidate!=name]
                status='resolved' if candidates else ('external' if not spec['module'].startswith('.') else 'unresolved')
            else:
                candidates,status=resolver.resolve(name,spec)
                candidates=[candidate for candidate in candidates if candidate!=name]
            if candidates:
                neighbours.update(candidates)
                if status.startswith('ambiguous'):notes.add('ts-alias-ambiguous:'+spec['module'])
                if status.endswith('+dynamic'):notes.add('ts-dynamic-import-resolved:'+spec['module'])
                if status=='workspace-package-not-indexed':notes.add('ts-workspace-package-not-indexed')
                continue
            unresolved.add(spec['module'])
            if status=='external':external.add(spec['module'])
            if status.endswith('unresolved'):notes.add('ts-resolution-unresolved:'+spec['module'])
            if status.endswith('refused'):notes.add('ts-resolution-refused:'+spec['module'])
            if status=='workspace-package-not-indexed':notes.add('ts-workspace-package-not-indexed')
    return dict(entry,neighbours=sorted(neighbours),unresolved=sorted(unresolved)[:MAX_IMPORTS],
                external=sorted(external)[:MAX_IMPORTS],notes=sorted(set(entry['notes'])|notes),
                complete=entry['complete'] and not unresolved)


def cache_paths(root):
    import workflow as w
    folder=Path(root)/'.crewloom'/'index'
    cache=w.safe_path(root,CACHE_RELATIVE,internal=True)
    for candidate in (Path(root)/'.crewloom',folder,cache):
        if candidate.is_symlink():raise ValueError('Map cache cannot use symlinks')
    return folder,cache


def scope_for(root, config):
    """Configured source roots and exclusions control the scan; escapes and links are refused."""
    if not config:
        return [''], set(EXCLUDED)
    roots = []
    for entry in config.get('source_roots') or ['.']:
        if not isinstance(entry, str) or not entry.strip() or Path(entry).is_absolute() or '..' in Path(entry).parts:
            raise ValueError('source_roots entries must be project-relative directories')
        current = root
        for part in Path(entry).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('source_roots entries may not be symlinks: ' + entry)
        candidate = current.resolve()
        if candidate != root and not candidate.is_relative_to(root):
            raise ValueError('source_roots entries may not escape the canonical project root: ' + entry)
        if not candidate.is_dir():
            raise ValueError('source_roots entry is not a directory: ' + entry)
        roots.append('' if entry in ('.', './') else entry.rstrip('/'))
    excluded = set(EXCLUDED) | set(config.get('exclude') or ())
    return (roots or ['']), excluded


def read_cache(cache,root,scope):
    """Corrupt caches rebuild; unbound caches adopt a new binding; foreign identity blocks writes."""
    if not cache.exists():return {},'absent'
    if cache.is_symlink() or cache.stat().st_nlink!=1:raise ValueError('Map cache must be a regular file without hardlinks')
    if cache.stat().st_size>8*MAX_FILE:raise ValueError('Map cache exceeds budget')
    try:value=json.loads(cache.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {},'recovered-corrupt-cache'
    if not isinstance(value,dict):return {},'recovered-corrupt-cache'
    if value.get('project_root')!=str(root):raise ValueError('Map cache belongs to another project')
    if (value.get('project_id'),value.get('checkout_id'))!=(scope['project_id'],scope['checkout_id']):
        if value.get('project_id') is None and value.get('checkout_id') is None:return {},'rebuilt-unbound-cache'
        raise ValueError('Map cache belongs to another project or checkout')
    if value.get('generation')==GENERATION_VERSION and value.get('schema_version')==SCHEMA_VERSION:
        files=value.get('files')
        if isinstance(files,dict):return files,'reused-generation'
    return {},'rebuilt-new-generation'


def inventory(root, state, source_roots, excluded):
    """The exact candidate set this index would scan: same scope, exclusions, caps and skips.

    Freshness checks reuse this so a change outside the configured scope, or in an excluded
    or oversized file, never invalidates a frozen generation while an in-scope create, delete
    or rename always does. Scan caps are enforced exactly where `build` enforces them, before
    the candidate is read, so an over-budget project can never look fresh. Every byte a
    candidate costs the index counts against the aggregate budget, including bytes the
    decoder later rejects: unreadable files must not buy unbounded reads.
    """
    selected=[];total=0
    for name in state['names']:
        parts=Path(name).parts
        if excluded.intersection(parts) or Path(name).suffix not in EXTENSIONS:continue
        if not any(not prefix or name==prefix or name.startswith(prefix+'/') for prefix in source_roots):continue
        path=Path(root).joinpath(*parts)
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1:continue
            size=path.stat().st_size
        except OSError:continue
        if size>MAX_FILE:continue
        if len(selected)>=MAX_FILES or total+size>MAX_TOTAL:
            raise ValueError('Repository map scan budget exceeded; split the project')
        # `build` charges every byte it reads, including bytes a failing decode discards.
        total+=size
        try:
            # A file the parser would skip is not part of the inventory either.
            path.read_bytes().decode('utf-8')
        except (OSError, UnicodeError):continue
        selected.append(name)
    return sorted(selected)


def module_configuration(root, state, excluded):
    """Read and validate every module configuration in scope before the index is written.

    Resolution depends on configuration, so a hostile or cyclic `extends` chain must fail
    before any generation is published rather than after edges were computed from it. Only
    exclusions apply here: a configuration governs the sources beneath it, so it is read
    even when `source_roots` does not cover its own directory.
    """
    names=[name for name in state['names']
           if Path(name).name in js_syntax.CONFIG_NAMES and not excluded.intersection(Path(name).parts)]
    return js_syntax.Resolver(root,names,excluded)


def module_configuration_digest(root, config=None):
    """The fingerprint of the module configuration in scope, without parsing a source file.

    Resolution depends on this configuration, so a frozen generation records the digest it
    resolved against. Rewriting an alias target or a workspace package entry point moves every
    edge it decides while leaving every source hash untouched, so this is the only signal that
    the navigation a task was given no longer describes the project. Only the bounded
    configuration files are read, which keeps the check cheap enough for a publication gate.
    """
    root = Path(root).resolve()
    state = git_state(root)
    _, excluded = scope_for(root, config)
    return module_configuration(root, state, excluded).config_sha256


def build(root,rebuild=False,config=None):
    """Re-hash every indexed candidate, reuse unchanged parses and write one atomic generation."""
    import workflow as w
    started=time.monotonic()
    root=Path(root).resolve()
    if not root.is_dir():raise ValueError('Explicit existing project root required')
    scope=identity(root)
    source_roots,excluded=scope_for(root,config)
    folder,cache=cache_paths(root)
    prior,prior_state=({},'rebuilt-forced') if rebuild else read_cache(cache,root,scope)
    state=git_state(root)
    # Configuration is read and validated first: an invalid one must never reach a generation.
    resolver=module_configuration(root,state,excluded)
    files={};entries={};total=0;reused=0;parsed=0;skipped=0
    for name in state['names']:
        parts=Path(name).parts
        if excluded.intersection(parts) or Path(name).suffix not in EXTENSIONS:continue
        if not any(not prefix or name==prefix or name.startswith(prefix+'/') for prefix in source_roots):continue
        if any((root.joinpath(*parts[:i])).is_symlink() for i in range(1,len(parts)+1)):
            raise ValueError('Mapped paths cannot use symlinks')
        path=w.safe_path(root,name)
        if not path.exists():continue
        if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('Map requires regular files without hardlinks')
        if path.stat().st_size>MAX_FILE:skipped+=1;continue
        if len(files)>=MAX_FILES or total+path.stat().st_size>MAX_TOTAL:raise ValueError('Repository map scan budget exceeded; split the project')
        raw=path.read_bytes();total+=len(raw);fingerprint=hashlib.sha256(raw).hexdigest()
        previous=prior.get(name)
        if (previous and previous.get('sha256')==fingerprint
                and previous.get('parser_version')==PARSER_VERSIONS.get(previous.get('parser'))
                and not previous.get('stale')):
            entry=dict(previous);reused+=1
        else:
            try:text=raw.decode('utf-8')
            except UnicodeError:skipped+=1;continue
            entry=structure(name,text);entry['sha256']=fingerprint
            entry['parser_version']=PARSER_VERSIONS.get(entry['parser'],0);parsed+=1
        files[name]=None;entries[name]=entry
    resolver.bind(files)
    for name in sorted(files):
        files[name]=link(name,entries[name],files,resolver)
    ordered=files
    renamed=[{'from':old,'to':new} for new,old in sorted(state['renamed'].items()) if new in ordered]
    incomplete=sorted(name for name,entry in ordered.items() if not entry['complete'])
    unsupported=sorted({note for entry in ordered.values() for note in entry['notes']}|set(resolver.notes))
    value={'generation':GENERATION_VERSION,'schema_version':SCHEMA_VERSION,
           'project_root':str(root),'project_id':scope['project_id'],'checkout_id':scope['checkout_id'],
           'parser_versions':PARSER_VERSIONS,'git':{'branch':state['branch'],'head':state['head']},
           'prior_state':prior_state,'stale':False,'files':ordered,
           'syntax':js_syntax.capability(JS_GRAMMAR),'config_sha256':resolver.config_sha256,
           'incomplete_files':incomplete,'unsupported':unsupported,'graph_complete':not incomplete}
    data=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
    if len(data)>8*MAX_FILE:raise ValueError('Map cache exceeds budget')
    folder.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder,delete=False) as stream:
        temporary=Path(stream.name);stream.write(data)
    os.replace(temporary,cache)
    legacy=w.safe_path(root,'.crewloom/repo-map.json',internal=True)
    migrated=False
    if legacy.is_file() and not legacy.is_symlink():
        legacy.unlink();migrated=True
    return value,{'files':len(ordered),'parsed':parsed,'reused':reused,'skipped':skipped,'scan_bytes':total,
                  'deleted':sorted(set(prior)-set(ordered))[:MAX_FILES],
                  'nominated':{'changed':len(state['changed']-state['deleted']),'untracked':len(state['untracked']),
                               'deleted':len(state['deleted']),'renamed':len(renamed)},
                  'renamed':renamed,'branch':state['branch'],'head':state['head'],'prior_state':prior_state,
                  'legacy_cache_migrated':migrated,
                  'generation':GENERATION_VERSION,'incomplete_files':len(incomplete),'graph_complete':not incomplete,
                  'syntax':value['syntax']['parser'],'config_sha256':resolver.config_sha256,
                  'duration_ms':round((time.monotonic()-started)*1000)}


def render(value,query,budget=8192,seeds=()):
    """Rank files, but always represent a seed path even when its symbol block is oversized."""
    if type(budget) is not int or not 1024<=budget<=65536:raise ValueError('Map budget must be 1024..65536 bytes')
    if isinstance(seeds,str):raise ValueError('Seeds must be a sequence of project-relative paths')
    seeds=list(seeds)
    if len(seeds)>MAX_SEEDS:raise ValueError('Too many seed files for one bounded map')
    words=set(re.findall(r'\w{3,}',query.casefold()));files=value['files']
    neighbours=set()
    for seed in seeds:
        neighbours.update(files.get(seed,{}).get('neighbours',()))
    missing=[seed for seed in seeds if seed not in files]
    def score(name):
        text=name+' '+' '.join(symbol['name'] for symbol in files[name]['symbols'])
        return (name in seeds,name in neighbours,len(words & set(re.findall(r'\w{3,}',text.casefold()))))
    ordered=sorted(files,key=lambda name:(tuple(-int(part) for part in score(name)),name))
    result=HEADER;included=0;truncated_seeds=[];missing_seeds=[]
    emitted=set()
    for name in [seed for seed in seeds if seed in files]+ordered:
        if name in emitted:continue
        emitted.add(name)
        entry=files[name]
        header=name+' ['+entry['parser']+' v'+str(entry.get('parser_version',0))+']\n'
        lines=[]
        for symbol in entry['symbols']:
            span=':'+str(symbol['line'])+('-'+str(symbol['end']) if symbol['end'] else '')
            lines.append('  '+symbol['kind']+' '+symbol['name']+span+'\n')
        block=header+''.join(lines)
        if len((result+block).encode())>budget:
            if name not in seeds:continue
            keep=lines[:MAX_SEED_SYMBOLS]
            while keep and len((result+header+''.join(keep)).encode())>budget:keep.pop()
            block=header+''.join(keep)+('  symbols omitted by budget; read the file\n' if entry['symbols'] else '')
            if len((result+block).encode())>budget:raise ValueError('Map budget too small for required seed paths')
            truncated_seeds.append(name)
        result+=block;included+=1
    missing_seeds=missing
    if missing_seeds:
        result+='Seed files absent from this index: '+', '.join(missing_seeds)+'\n'
    return result,{'included_files':included,'omitted_files':len(files)-included,'map_bytes':len(result.encode()),
                   'seed_files':len(seeds),'missing_seed_files':missing_seeds,
                   'truncated_seed_files':sorted(truncated_seeds),'graph_complete':value.get('graph_complete',False)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True);parser.add_argument('--query',default='')
    parser.add_argument('--budget',type=int,default=8192)
    parser.add_argument('--seed',action='append',default=[])
    parser.add_argument('--rebuild',action='store_true',help='Discard cached parses and re-index every candidate')
    args=parser.parse_args(argv)
    try:
        value,stats=build(Path(args.project),args.rebuild);text,selection=render(value,args.query,args.budget,args.seed)
        print(json.dumps({'map':text,'stats':dict(stats,**selection)},ensure_ascii=False));return 0
    except (ValueError,OSError,subprocess.SubprocessError) as exc:print(json.dumps({'error':str(exc)}));return 2


if __name__=='__main__':raise SystemExit(main())
