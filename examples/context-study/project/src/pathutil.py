"""Project-relative path component rules shared by the path modules.

Refusing one component is cheap; discovering afterwards that a write escaped the
project is not. Every decision the resolver needs is a pure function of the root
and the declared relative string, so the rules live here and are reused instead
of being restated at each call site.
"""
import os
from pathlib import Path, PurePosixPath

EMPTY = 'relative path is empty or contains a forbidden character'
ABSOLUTE = 'absolute path is not project-relative'
TRAVERSING = 'relative path contains a traversing component'


def split_relative(relative):
    """Split a declared project-relative path, refusing unsafe component shapes.

    Absolute paths, parent traversal, NUL bytes, backslashes and dot-only paths
    are refused here, before any filesystem access, so a hostile declaration
    cannot reach ``stat`` at all.
    """
    if not isinstance(relative, str):
        raise TypeError('relative must be a string')
    if not relative or '\x00' in relative or '\\' in relative:
        raise ValueError(EMPTY)
    if os.path.isabs(relative) or relative.startswith('/'):
        raise ValueError(ABSOLUTE)
    parts = PurePosixPath(relative).parts
    if not parts:
        raise ValueError(EMPTY)
    for part in parts:
        if part in ('', '.', '..'):
            raise ValueError(TRAVERSING)
    return parts


def is_linked(root, parts):
    """True when any component below the root is a symbolic link.

    A link is refused even when it resolves inside the project: the destination
    is no longer the declared path, and a later retarget would move the write.
    """
    current = Path(root)
    for part in parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def is_hardlinked(path):
    """True for an existing regular file with more than one directory entry."""
    path = Path(path)
    try:
        return path.is_file() and path.stat().st_nlink > 1
    except OSError:
        return False


def regular_file_below(root, parts):
    """The shallowest existing regular file among the parent components, or None.

    A regular file used as a directory means the declaration cannot exist now
    and cannot be created later either, so it is refused up front.
    """
    current = Path(root)
    for part in parts[:-1]:
        current = current / part
        if current.is_file() and not current.is_symlink():
            return current
    return None


def contained(root, path):
    """True when a resolved absolute path stays inside the project root."""
    root = Path(root).resolve()
    try:
        resolved = Path(path).resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents