"""Trusted artifact broker: containers see declared files, never the project mount."""
import os
from pathlib import Path
import tempfile

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_ARTIFACTS = 128


def destinations(root, outputs):
    import workflow as w
    if len(outputs)>MAX_ARTIFACTS:raise ValueError('Too many output artifacts')
    found={}
    for relative in outputs:
        current=root
        for part in Path(relative).parts:
            current=current/part
            if current.is_symlink():raise ValueError('Output paths may not use symlinks')
        path=w.safe_path(root,relative)
        if path.is_relative_to(w.LIBRARY):raise ValueError('Trusted Crewloom runtime is read-only; use a separate project/worktree')
        if path in found.values():raise ValueError('Output aliases are forbidden')
        if path.exists() and (not path.is_file() or path.stat().st_nlink!=1):
            raise ValueError('Output must be a regular file without hardlinks')
        found[relative]=path
    return found


def publish(root, artifacts, expected_inputs):
    import workflow as w
    if w.hashes(root,list(expected_inputs))!=expected_inputs:
        raise ValueError('Inputs changed during execution; artifacts rejected')
    targets=destinations(root,list(artifacts))
    if any(not isinstance(data,bytes) or not data for data in artifacts.values()):
        raise ValueError('Outputs must be nonempty regular files')
    if sum(len(data) for data in artifacts.values())>MAX_OUTPUT_BYTES:
        raise ValueError('Output artifact budget exceeded')
    for relative,target in targets.items():
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as stream:
            temporary=Path(stream.name);stream.write(artifacts[relative])
        os.replace(temporary,target)


def execute(root, step, image_id, timeout):
    import workflow as w
    outputs=destinations(root,step['outputs'])
    if len(step['inputs'])>MAX_ARTIFACTS:raise ValueError('Too many input artifacts')
    expected=w.hashes(root,step['inputs'])
    if any(w.safe_path(root,p).stat().st_nlink!=1 for p in step['inputs']):raise ValueError('Hardlinked inputs are forbidden')
    total=sum(w.safe_path(root,p).stat().st_size for p in step['inputs'])
    if total>MAX_INPUT_BYTES:raise ValueError('Input artifact budget exceeded')
    with tempfile.TemporaryDirectory(prefix='crewloom-command-') as directory:
        stage=Path(directory).resolve();(stage/'.crewloom').mkdir()
        for relative in step['inputs']:
            target=w.safe_path(stage,relative);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(w.safe_path(root,relative).read_bytes())
        writable=[]
        for relative in outputs:
            target=w.safe_path(stage,relative);target.parent.mkdir(parents=True,exist_ok=True)
            if relative not in step['inputs']:target.write_bytes(b'')
            writable.append(relative)
        before={relative:(w.safe_path(stage,relative).stat().st_mtime_ns,w.safe_path(stage,relative).stat().st_size) for relative in outputs}
        result=w.docker_execute(stage,step['argv'],image_id,timeout,writable=writable)
        result['boundary']='declared-input snapshot; read-only workspace; declared output file mounts'
        if result['exit_code']:return result
        artifacts={}
        for relative in outputs:
            target=w.safe_path(stage,relative)
            if target.is_symlink() or not target.is_file() or target.stat().st_nlink!=1:
                raise ValueError('Output must be a regular file without links')
            if (target.stat().st_mtime_ns,target.stat().st_size)==before[relative]:raise ValueError('Unchanged output is not fresh execution evidence')
            if target.stat().st_size>MAX_OUTPUT_BYTES:raise ValueError('Output artifact budget exceeded')
            artifacts[relative]=target.read_bytes()
        publish(root,artifacts,expected)
        return result
