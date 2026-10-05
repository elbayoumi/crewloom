#!/usr/bin/env python3
"""One explicit resolver for Crewloom resources in a checkout or an installed wheel.

A source checkout keeps role trees inside the repository; an installed distribution maps
the repository root into one ``crewloom_data`` directory beside the flat CLI modules.
Installed roles therefore keep the depth they have in a checkout, so role scripts that
climb to their own installation root resolve the installed tree unchanged.

Every caller asks this module instead of guessing a checkout root, so a wheel, an sdist,
an editable install and a repository-native run all resolve the same files without
reading the working directory or depending on an editable path staying put. Roles and
documentation live in exactly one place in the source tree; nothing is copied twice.
"""
import importlib.util
import os
from pathlib import Path, PurePosixPath

DATA_PACKAGE = 'crewloom_data'
MODULE_DIR = Path(__file__).resolve().parent
ROLES_DIRECTORY = Path('.agents') / 'skills'
DOCUMENTATION_DIRECTORY = 'documentation'
SCRIPTS_DIRECTORY = 'scripts'
MISSING = ('Crewloom resources are unavailable. Reinstall the distribution with '
           '`pip install --force-reinstall crewloom`, or run from a Crewloom source '
           'checkout or unpacked sdist.')


class ResourceError(RuntimeError):
    """Raised when installed resources are absent, incomplete, or a lookup escapes them."""


def _source_root():
    """The checkout root when this module directory has a role tree beside it."""
    roles = MODULE_DIR.parent / ROLES_DIRECTORY
    if roles.is_dir() and any(roles.glob('*/SKILL.md')):
        return MODULE_DIR.parent
    return None


def _packaged_root():
    """The installed data directory, found without guessing an interpreter layout."""
    try:
        spec = importlib.util.find_spec(DATA_PACKAGE)
    except (ImportError, ValueError):
        return None
    for location in list(getattr(spec, 'submodule_search_locations', None) or ()):
        if Path(location).is_dir():
            return Path(location)
    return None


def layout():
    """Return (distribution root, roles directory, documentation directory, from checkout)."""
    source = _source_root()
    if source is not None:
        return source, source / ROLES_DIRECTORY, source / DOCUMENTATION_DIRECTORY, True
    packaged = _packaged_root()
    if packaged is not None:
        return packaged, packaged / ROLES_DIRECTORY, packaged / DOCUMENTATION_DIRECTORY, False
    raise ResourceError(MISSING)


def source_checkout():
    """True when resources come from a repository checkout rather than installed data."""
    return layout()[3]


def distribution_root():
    """Root of the resources this installation serves."""
    return layout()[0]


def roles_dir():
    """Directory holding the 42 role trees, each with SKILL.md, memory, and references."""
    return layout()[1]


def documentation_dir():
    """Directory holding the runtime registry and the public English documentation."""
    return layout()[2]


def role_ids():
    """Sorted role identifiers discovered from the resolved role directory."""
    directory = roles_dir()
    return sorted(path.parent.name for path in directory.glob('*/SKILL.md'))


def role_dir(ident):
    """One role directory, or a diagnostic instead of a bare missing-file failure."""
    if not isinstance(ident, str) or not ident or '/' in ident or ident in ('.', '..'):
        raise ResourceError('Invalid role identifier')
    path = roles_dir() / ident
    if not (path / 'SKILL.md').is_file():
        raise ResourceError('Role is not part of this installation: ' + ident)
    return path


def module_file(name):
    """One sibling CLI module of the installed distribution."""
    if not isinstance(name, str) or not name.endswith('.py') or '/' in name or '\\' in name:
        raise ResourceError('Invalid module name')
    return MODULE_DIR / name


def _relative_parts(relative):
    parts = PurePosixPath(str(relative).replace(os.sep, '/')).parts
    if not parts or PurePosixPath(str(relative).replace(os.sep, '/')).is_absolute() or '..' in parts:
        raise ResourceError('Resource path must stay inside the distribution: ' + str(relative))
    return parts


def resolve(relative):
    """Map one repository-relative resource path to its real installed location."""
    parts = _relative_parts(relative)
    root, roles, documentation, _ = layout()
    if parts[:2] == tuple(ROLES_DIRECTORY.parts):
        return roles.joinpath(*parts[2:])
    if parts[:1] == (SCRIPTS_DIRECTORY,):
        return MODULE_DIR.joinpath(*parts[1:])
    if parts[:1] == (DOCUMENTATION_DIRECTORY,):
        return documentation.joinpath(*parts[1:])
    return root.joinpath(*parts)


def require(relative, label='Crewloom resource'):
    """Resolve a resource that must exist, naming what is absent instead of a traceback."""
    path = resolve(relative)
    if not path.exists():
        raise ResourceError(f'{label} is not part of this installation: {relative}')
    return path


def installed_roots():
    """Every directory a resolved resource is allowed to live in."""
    _, roles, documentation, _ = layout()
    return (MODULE_DIR, roles, documentation)


def dashboard_dir():
    """The Node dashboard sources, which ship with a checkout or sdist but not the wheel."""
    source = _source_root()
    if source is None:
        raise ResourceError(
            'The dashboard is not bundled in the Python distribution because its Node '
            'dependencies are not. Start it from a Crewloom checkout or unpacked sdist '
            '(`cd dashboard && npm install && npm run dev`), or point CREWLOOM_ROOT at '
            'such a checkout when running the installed CLI.')
    folder = source / 'dashboard'
    if not (folder / 'package.json').is_file():
        raise ResourceError('Dashboard sources are incomplete: ' + str(folder))
    return folder