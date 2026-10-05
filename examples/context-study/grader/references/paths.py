"""Project-contained resolution for a declared relative path."""
from pathlib import Path

from src.pathutil import contained, is_hardlinked, is_linked, regular_file_below, split_relative


def resolve_project_path(root, relative):
    """Resolve one declared project-relative path, refusing every escape."""
    if not isinstance(root, Path):
        raise TypeError('root must be a pathlib.Path')
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('root must be an existing absolute directory')
    parts = split_relative(relative)
    if regular_file_below(root, parts) is not None:
        raise ValueError('a parent component is a regular file')
    if is_linked(root, parts):
        raise ValueError('a path component is a symbolic link')
    target = root.joinpath(*parts)
    if is_hardlinked(target):
        raise ValueError('destination is a hardlinked file')
    if not contained(root, target):
        raise ValueError('destination escapes the project root')
    return target
