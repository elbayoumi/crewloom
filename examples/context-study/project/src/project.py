"""Declared project layout, built on the shared path rules.

Every location this project writes is declared project-relative first, so the
resolver in ``src/paths.py`` is the single place that turns a declaration into a
real filesystem path. Keeping the declarations here means a reviewer can audit
what the project is allowed to touch without reading the resolver.
"""
from src.pathutil import split_relative

SOURCE_ROOT = 'src'
CONTROL_FILES = ('crewloom.project.json', '.crewloom/binding.json')


def source_paths(names):
    """Declared artifacts placed under the source root."""
    return [SOURCE_ROOT + '/' + '/'.join(split_relative(name)) for name in names]


def report_path(name):
    """One declared report location, which may live outside the source root."""
    return '/'.join(split_relative(name))


def control_path(name):
    """A control file location; these are reserved and never generated."""
    if name in CONTROL_FILES:
        raise ValueError('control file location is reserved: ' + name)
    return name


def is_control(name):
    """True for a reserved project control location."""
    return name in CONTROL_FILES