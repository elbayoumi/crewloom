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

from __future__ import annotations

import importlib.util
import os
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple, Union

DATA_PACKAGE: str = "crewloom_data"
MODULE_DIR: Path = Path(__file__).resolve().parent
ROLES_DIRECTORY: Path = Path(".agents") / "skills"
DOCUMENTATION_DIRECTORY: str = "documentation"
SCRIPTS_DIRECTORY: str = "scripts"
MISSING: str = (
    "Crewloom resources are unavailable. Reinstall the distribution with "
    "`python -m pip install --force-reinstall /path/to/crewloom`, or run from a Crewloom source "
    "checkout or unpacked sdist."
)


class ResourceError(RuntimeError):
    """Raised when installed resources are absent, incomplete, or a lookup escapes them."""


def _source_root() -> Optional[Path]:
    """Return the checkout root when this module directory has a role tree beside it."""
    roles = MODULE_DIR.parent / ROLES_DIRECTORY
    if roles.is_dir() and any(roles.glob("*/SKILL.md")):
        return MODULE_DIR.parent
    return None


def _packaged_root() -> Optional[Path]:
    """Return the installed data directory, found without guessing an interpreter layout."""
    try:
        spec = importlib.util.find_spec(DATA_PACKAGE)
    except (ImportError, ValueError):
        return None
    for location in list(getattr(spec, "submodule_search_locations", None) or ()):
        candidate = Path(location)
        if candidate.is_dir():
            return candidate
    return None


def layout() -> Tuple[Path, Path, Path, bool]:
    """Return (distribution root, roles directory, documentation directory, from checkout)."""
    source = _source_root()
    if source is not None:
        return source, source / ROLES_DIRECTORY, source / Path(DOCUMENTATION_DIRECTORY), True
    packaged = _packaged_root()
    if packaged is not None:
        return packaged, packaged / ROLES_DIRECTORY, packaged / Path(DOCUMENTATION_DIRECTORY), False
    raise ResourceError(MISSING)


def source_checkout() -> bool:
    """Return True when resources come from a repository checkout rather than installed data."""
    return layout()[3]


def distribution_root() -> Path:
    """Return the root path of the resources this installation serves."""
    return layout()[0]


def roles_dir() -> Path:
    """Return the directory holding the 44 role trees, each with SKILL.md, memory, and references."""
    return layout()[1]


def documentation_dir() -> Path:
    """Return the directory holding the runtime registry and the public English documentation."""
    return layout()[2]


def role_ids() -> List[str]:
    """Return sorted role identifiers discovered from the resolved role directory."""
    directory = roles_dir()
    return sorted(path.parent.name for path in directory.glob("*/SKILL.md"))


def role_dir(ident: str) -> Path:
    """Return one role directory, or raise ResourceError instead of bare missing-file failure."""
    if (
        not isinstance(ident, str)
        or not ident
        or "/" in ident
        or "\\" in ident
        or "\0" in ident
        or ident in (".", "..")
    ):
        raise ResourceError("Invalid role identifier")
    path = roles_dir() / ident
    if not (path / "SKILL.md").is_file():
        raise ResourceError("Role is not part of this installation: " + ident)
    return path


def module_file(name: str) -> Path:
    """Return one sibling CLI module of the installed distribution."""
    if (
        not isinstance(name, str)
        or not name.endswith(".py")
        or "/" in name
        or "\\" in name
        or "\0" in name
    ):
        raise ResourceError("Invalid module name")
    return MODULE_DIR / name


def _relative_parts(relative: Union[str, Path, PurePosixPath]) -> Tuple[str, ...]:
    """Safely parse and validate path parts, refusing path escapes and NUL bytes."""
    normalized = str(relative).replace("\\", "/").replace(os.sep, "/")
    if "\0" in normalized:
        raise ResourceError("Resource path must stay inside the distribution: " + str(relative))
    parts = PurePosixPath(normalized).parts
    if not parts or PurePosixPath(normalized).is_absolute() or ".." in parts:
        raise ResourceError("Resource path must stay inside the distribution: " + str(relative))
    return parts


def resolve(relative: Union[str, Path, PurePosixPath]) -> Path:
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


def require(relative: Union[str, Path, PurePosixPath], label: str = "Crewloom resource") -> Path:
    """Resolve a resource that must exist, naming what is absent instead of a traceback."""
    path = resolve(relative)
    if not path.exists():
        raise ResourceError(f"{label} is not part of this installation: {relative}")
    return path


def installed_roots() -> Tuple[Path, Path, Path]:
    """Return every directory a resolved resource is allowed to live in."""
    _, roles, documentation, _ = layout()
    return (MODULE_DIR, roles, documentation)


def dashboard_dir() -> Path:
    """Return the Node dashboard sources, which ship with a checkout or sdist but not the wheel."""
    source = _source_root()
    if source is None:
        raise ResourceError(
            "The dashboard is not bundled in the Python distribution because its Node "
            "dependencies are not. Start it from a Crewloom checkout or unpacked sdist "
            "(`cd dashboard && npm ci && npm run dev`)."
        )
    folder = source / "dashboard"
    if not (folder / "package.json").is_file():
        raise ResourceError("Dashboard sources are incomplete: " + str(folder))
    return folder