"""Build/check the source checkout's browser ZIP from its single extension tree.

Input: bounded regular public files under extensions/chrome. Output: one deterministic
assets/crewloom-chrome-extension.zip; atomic replacement. --check writes nothing and
returns 1 on stale/missing content. Redirected paths and oversized files are refused.
This source-maintenance command does not install an extension or publish a release.
"""
import argparse
import io
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024
PUBLIC_FILES = {'README.md', 'background.js', 'content.js', 'content.css', 'manifest.json',
                'sidepanel.js', 'sidepanel.html', 'sidepanel.css',
                *(f'icons/icon-{size}.png' for size in (16, 32, 48, 128))}


def files(root):
    directory = root / 'extensions' / 'chrome'
    if not directory.is_dir():
        raise ValueError('Browser source tree is unavailable')
    contents = {}
    for path in sorted(directory.rglob('*')):
        if any(part.startswith('.') for part in path.relative_to(directory).parts):
            continue
        current = path
        while current != root:
            if current.is_symlink():
                raise ValueError('Browser package may not follow symlinks')
            current = current.parent
        if path.is_dir():
            continue
        if path.relative_to(directory).as_posix() not in PUBLIC_FILES:
            raise ValueError('Unreviewed file in browser source: ' + path.name)
        if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > MAX_BYTES:
            raise ValueError('Browser input must be a bounded single-link regular file')
        contents['chrome/' + path.relative_to(directory).as_posix()] = path.read_bytes()
    if not contents or sum(map(len, contents.values())) > MAX_BYTES:
        raise ValueError('Browser source package is empty or exceeds 2 MiB')
    if set(contents) != {'chrome/' + name for name in PUBLIC_FILES}:
        raise ValueError('Browser source package is missing declared public files')
    return contents


def target(root):
    path = root / 'assets' / 'crewloom-chrome-extension.zip'
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Browser ZIP destination may not follow symlinks')
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('Browser ZIP destination must be a single-link regular file')
    return path


def check(root):
    contents = files(root)
    path = target(root)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        return ['Browser ZIP is missing or oversized']
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) != len(contents) or set(archive.namelist()) != set(contents):
                return ['Browser ZIP inventory differs from source']
            return ['Browser ZIP differs: ' + name for name, data in contents.items()
                    if archive.getinfo(name).file_size != len(data) or archive.read(name) != data]
    except (OSError, ValueError, zipfile.BadZipFile):
        return ['Browser ZIP is malformed']


def build(root):
    contents = files(root)
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content)
    path = target(root)
    path.parent.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data.getvalue())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return path


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        if not args.check:
            build(root)
        problems = check(root)
        for problem in problems:
            print(problem)
        if not problems:
            print('PASS: browser ZIP matches the extension source')
        return int(bool(problems))
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
