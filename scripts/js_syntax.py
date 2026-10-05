"""Real JS/TS syntax trees and bounded project-local module resolution.

Installing the optional ``crewloom[syntax]`` extra adds Tree-sitter plus the JavaScript and
TypeScript grammars. With them :func:`extract` reads definitions and module specifiers from
the concrete syntax tree, so declarations hidden in comments, string and template literals
are not navigation symbols, and nested methods, arrows, interfaces and re-exports are found
at any depth. Without the extra every caller keeps the labelled approximate extraction and
the generated map still records which parser produced it.

Resolution is deliberately project-local and bounded. Relative specifiers resolve against
the indexed file set; ``tsconfig`` ``baseUrl``/``paths`` aliases resolve against the nearest
project-local configuration; workspace-local packages resolve through their own declared
``exports`` or entry points. A specifier naming something outside the project is reported as
external and one this resolver cannot follow is reported as unresolved, so a partial graph is
never presented as a complete one.

Every configuration in scope is read and validated before the index is written: ``extends``
may only name a canonical project file, an escaping or cyclic chain is refused, and a
package-name ``extends`` this resolver cannot read is recorded as a note instead of being
silently applied.
"""
import hashlib
import json
import posixpath
from pathlib import Path

EXTRA = 'crewloom[syntax]'
PACKAGES = ('tree-sitter', 'tree-sitter-javascript', 'tree-sitter-typescript')
# Bumped whenever the meaning of a symbol, import or note changes, so a cached parse from an
# older contract is rebuilt instead of being reused with the previous semantics.
EXTRACTION_VERSION = 3
GRAMMARS = {'.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
            '.ts': 'typescript', '.tsx': 'tsx', '.mts': 'typescript', '.cts': 'typescript'}
# Resolution prefers TypeScript sources, the way a project declares its own aliases.
RESOLVE_EXTENSIONS = ('.ts', '.tsx', '.mts', '.cts', '.d.ts', '.js', '.jsx', '.mjs', '.cjs')
DECLARATIONS = {'function_declaration': 'function', 'generator_function_declaration': 'function',
                'function_signature': 'function', 'class_declaration': 'class',
                'abstract_class_declaration': 'class', 'method_definition': 'method',
                'method_signature': 'method', 'abstract_method_signature': 'method',
                'interface_declaration': 'interface', 'type_alias_declaration': 'type',
                'enum_declaration': 'enum', 'module': 'namespace', 'internal_module': 'namespace'}
FUNCTION_VALUES = {'arrow_function': 'arrow', 'function_expression': 'function',
                   'function': 'function', 'generator_function': 'function'}
BINDINGS = ('variable_declarator', 'field_definition', 'public_field_definition')
IDENTIFIER_TYPES = ('identifier', 'property_identifier')
DECLARATION_KEYWORDS = ('const', 'let', 'var')
CONFIG_NAMES = ('tsconfig.json', 'package.json')
# Runtime state and Git internals are never module configuration: an `extends` chain that
# reaches one would let a step read the reviewer issuance authority or another checkout's
# objects by naming it as a compiler option file.
PROTECTED = ('.crewloom', '.git')
MAX_CONFIG_BYTES = 256 * 1024
# A per-file cap alone is not a budget: sixty-four allowed configurations would still admit
# sixteen megabytes of configuration, so every configuration read is charged here.
MAX_TOTAL_CONFIG_BYTES = 1024 * 1024
MAX_NODES = 400000
MAX_CONFIGS = 64
MAX_EXTENDS = 16
MAX_PACKAGES = 128
MAX_WILDCARD = 1
CONDITIONS = ('types', 'import', 'require', 'node', 'default')
# A note that means the extracted graph is a strict subset of what the file contains. Any of
# them keeps the generation out of the complete-graph claim instead of hiding the gap.
INCOMPLETE = frozenset({'ts-syntax-error-partial', 'ts-parse-budget-exceeded',
                        'ts-import-without-literal-source', 'ts-indirect-module-call-not-resolved'})
_LANGUAGES = {}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def versions():
    """Installed parser and grammar versions, or ``None`` when the extra is absent."""
    import importlib.metadata as metadata
    found = {}
    for package in PACKAGES:
        try:
            found[package] = metadata.version(package)
        except Exception:  # A missing or unreadable distribution is an absent extra.
            return None
    return found


def revision():
    """One integer cache key covering the exact parser, grammars and extraction contract.

    Parse reuse compares this value with the one stored in the cached generation, so a grammar
    upgrade or a change in extraction semantics re-parses every candidate while an unchanged
    grammar under an unchanged contract reuses it.
    """
    found = versions()
    if found is None:
        return 0
    return int(digest(json.dumps(dict(found, extraction=EXTRACTION_VERSION), sort_keys=True).encode())[:12], 16)


def languages():
    """The three grammars, or ``None`` when the optional extra is not installed."""
    if 'value' in _LANGUAGES:
        return _LANGUAGES['value']
    value = None
    try:
        import tree_sitter_javascript
        import tree_sitter_typescript
        from tree_sitter import Language
        value = {'javascript': Language(tree_sitter_javascript.language()),
                 'typescript': Language(tree_sitter_typescript.language_typescript()),
                 'tsx': Language(tree_sitter_typescript.language_tsx())}
    except Exception:  # Any import or ABI failure is an absent extra, never a broken map.
        value = None
    _LANGUAGES['value'] = value
    return value


def available():
    """Whether real JS/TS extraction is available in this installation."""
    return languages() is not None


def capability(available=None):
    """What produced a generation: the extra's real versions, or the labelled fallback.

    `available` lets a caller state the extractor it actually used. The map passes the
    grammar selector, so a generation reports the parser that produced it rather than only
    what happens to be installed in this interpreter.
    """
    found = versions()
    if available is None:
        available = languages() is not None
    if not available or found is None:
        return {'available': False, 'extra': EXTRA, 'parser': 'approximate-js-ts',
                'note': 'Install ' + EXTRA + ' for real JavaScript and TypeScript syntax trees'}
    return {'available': True, 'extra': EXTRA, 'parser': 'ts-ast', 'packages': found,
            'revision': revision()}


def _text(node):
    if node is None:
        return None
    value = node.text.decode('utf-8', 'replace').strip()
    for quote in ('"', "'", '`'):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value


def _string(node):
    """The value of a JavaScript string literal, without its quote characters."""
    if node is None or node.type not in ('string', 'string_literal'):
        return None
    return _text(node)


def _is_type_only(node):
    return any(child.type == 'type' for child in node.children)


def _specifier_names(node):
    """Imported or re-exported binding names, for symbol-level navigation hints."""
    clauses = [child for child in node.named_children
               if child.type in ('import_clause', 'named_imports', 'export_clause')]
    names = []
    for clause in clauses:
        parts = [clause] if clause.type in ('named_imports', 'export_clause') else list(clause.named_children)
        for part in parts:
            if part.type in ('import_specifier', 'export_specifier'):
                identifier = part.child_by_field_name('alias') or part.child_by_field_name('name')
                names.append(_text(identifier or part))
            elif part.type in ('namespace_import', 'namespace_export', 'identifier'):
                names.append(_text(part))
    return [name for name in names if name and ' ' not in name]


def _module_call(node):
    """Classify a call as a module load, or as an ordinary call worth no note at all.

    A literal ``require('x')`` or dynamic ``import('x')`` returns its module string. A module
    load whose argument is computed cannot be followed from the tree, which is a real gap in
    the dependency graph and is reported as one. Every other call is an ordinary function
    invocation: ``Math.abs(x)`` says nothing about module edges, and labelling it an
    unresolved module import would turn a complete graph into an artificial partial one.
    """
    function = node.child_by_field_name('function')
    arguments = node.child_by_field_name('arguments')
    if function is None or arguments is None or len(arguments.named_children) != 1:
        return None
    name = _text(function)
    if name not in ('require', 'import'):
        return None
    return ('require' if name == 'require' else 'dynamic'), _string(arguments.named_children[0])


def _binding_name(node):
    """The single name a declarator or class field binds, or ``None`` for a pattern.

    A destructuring pattern binds several names at once, and its source text is not any one of
    them. Reporting it would put a name in the map that cannot be searched for or navigated to,
    so a pattern is skipped and the surrounding declaration is still visible in the file.
    """
    name = node.child_by_field_name('name')
    if name is None:
        name = next((child for child in node.children if child.type in IDENTIFIER_TYPES), None)
    if name is None or name.type not in IDENTIFIER_TYPES:
        return None
    return _text(name)


def _binding(node):
    """One named binding, labelled the way a reader would search the map for it.

    A binding whose value is a function keeps that function's kind, so an arrow assigned to a
    constant is labelled the same as a declared function. Every other binding is labelled with
    its declaration keyword: in JavaScript and TypeScript an exported constant is part of a
    module's surface, and hiding it would make the real extractor report strictly less than the
    approximate fallback it replaces.
    """
    name = _binding_name(node)
    if not name:
        return None
    value = node.child_by_field_name('value')
    if value is not None and value.type in FUNCTION_VALUES:
        return name, FUNCTION_VALUES[value.type]
    if node.type in ('field_definition', 'public_field_definition'):
        return name, 'field'
    parent = node.parent
    keyword = _text(parent.child_by_field_name('kind')) if parent is not None else None
    return name, keyword if keyword in DECLARATION_KEYWORDS else 'binding'


def extract(name, text):
    """Definitions and module specifiers from the real syntax tree of one file.

    A Tree-sitter parse never fails: an incomplete or invalid file yields the declarations
    the grammar could still recognise plus an explicit note, so a broken file stays visible
    instead of disappearing from navigation.
    """
    found = languages()
    if found is None:
        raise ValueError('Real syntax extraction requires the ' + EXTRA + ' extra')
    import tree_sitter
    kind = GRAMMARS.get(Path(name).suffix)
    if kind is None:
        raise ValueError('No grammar for ' + name)
    parser = tree_sitter.Parser(found[kind])
    tree = parser.parse(text.encode('utf-8'))
    symbols = []
    imports = []
    notes = []
    visited = 0
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        visited += 1
        if visited > MAX_NODES:
            notes.append('ts-parse-budget-exceeded')
            break
        declared = DECLARATIONS.get(node.type)
        if declared:
            identifier = _text(node.child_by_field_name('name'))
            if identifier:
                symbols.append({'name': identifier, 'line': node.start_point[0] + 1,
                                'end': node.end_point[0] + 1, 'kind': declared})
        elif node.type in BINDINGS:
            bound = _binding(node)
            if bound is not None:
                symbols.append({'name': bound[0], 'line': node.start_point[0] + 1,
                                'end': node.end_point[0] + 1, 'kind': bound[1]})
        elif node.type == 'import_statement':
            source = _string(node.child_by_field_name('source'))
            if source is None:
                notes.append('ts-import-without-literal-source')
            else:
                imports.append({'module': source,
                                'kind': 'import-type' if _is_type_only(node) else 'import',
                                'names': _specifier_names(node), 'raw': 'import ' + source})
        elif node.type == 'export_statement':
            source = _string(node.child_by_field_name('source'))
            if source is not None:
                imports.append({'module': source,
                                'kind': 'export-type' if _is_type_only(node) else 'export',
                                'names': _specifier_names(node), 'raw': 'export from ' + source})
            # The declaration continues below this statement, so its children are still
            # walked: `export interface` and `export function` must not disappear.
        elif node.type == 'call_expression':
            called = _module_call(node)
            if called is not None:
                if called[1] is None:
                    notes.append('ts-indirect-module-call-not-resolved')
                else:
                    imports.append({'module': called[1], 'kind': called[0], 'names': [],
                                    'raw': called[0] + ' ' + called[1]})
        stack.extend(reversed(node.children))
    if tree.root_node.has_error:
        notes.append('ts-syntax-error-partial')
    return {'symbols': symbols, 'imports': imports, 'notes': notes,
            'complete': not INCOMPLETE.intersection(notes)}


def _strip_comments(text):
    """Reduce TypeScript JSONC to strict JSON, as its own configuration reader accepts.

    A `tsconfig` is JSON with comments and trailing commas by specification, so refusing one
    because of either would refuse a file every real project ships. Strings are tracked, so a
    `//` or a comma inside a value is never mistaken for syntax.
    """
    out = []
    index = 0
    quote = None
    while index < len(text):
        char = text[index]
        if quote:
            out.append(char)
            if char == '\\' and index + 1 < len(text):
                out.append(text[index + 1]);index += 2;continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in '"\'':
            quote = char;out.append(char);index += 1;continue
        if char == '/' and index + 1 < len(text):
            following = text[index + 1]
            if following == '/':
                while index < len(text) and text[index] != '\n':
                    index += 1
                continue
            if following == '*':
                end = text.find('*/', index + 2)
                if end < 0:
                    raise ValueError('Unterminated comment in module configuration')
                index = end + 2
                continue
        if char == ',':
            ahead = index + 1
            while ahead < len(text) and text[ahead].isspace():
                ahead += 1
            if ahead < len(text) and text[ahead] in '}]':
                index += 1
                continue
        out.append(char)
        index += 1
    return ''.join(out)


def _canonical(root, relative):
    """One project-local real path, refusing protected, symlinked or escaping components."""
    parts = Path(relative).parts
    if any(part in PROTECTED for part in parts):
        raise ValueError('Module configuration may not read protected runtime state: ' + str(relative))
    current = Path(root)
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Module configuration may not use symlinks: ' + str(relative))
    resolved = current.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError('Module configuration escapes the canonical project root: ' + str(relative))
    return resolved


def _read_json(path, label, charged=None):
    """Read one bounded JSON/JSONC configuration and charge it to an aggregate budget.

    The size is refused from the directory entry before any byte is read, so an oversized
    configuration cannot buy an unbounded read by being discovered late. `charged` is the
    caller's running total in bytes: a single file under the cap must still not let the whole
    scope exceed the aggregate budget.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError('Unreadable ' + label + ': ' + path.name) from exc
    if size > MAX_CONFIG_BYTES:
        raise ValueError(label + ' exceeds the configuration budget: ' + path.name)
    if charged is not None:
        charged[0] += size
        if charged[0] > MAX_TOTAL_CONFIG_BYTES:
            raise ValueError('Module configurations exceed the aggregate budget; narrow source_roots')
    try:
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise ValueError('Unreadable ' + label + ': ' + path.name) from exc
    try:
        value = json.loads(_strip_comments(raw))
    except ValueError as exc:
        raise ValueError('Unreadable ' + label + ': ' + path.name) from exc
    if not isinstance(value, dict):
        raise ValueError(label + ' must be a JSON object: ' + path.name)
    return value


def _wildcard(pattern, value):
    """Match one ``*`` wildcard, returning the captured text or ``None``."""
    if pattern.count('*') != MAX_WILDCARD:
        return None
    prefix, _, suffix = pattern.partition('*')
    if value.startswith(prefix) and value.endswith(suffix) and len(value) >= len(prefix) + len(suffix):
        return value[len(prefix):len(value) - len(suffix)]
    return None


def _candidates(stem):
    """Every file name a resolved stem may stand for, in TypeScript preference order."""
    if not stem or stem.startswith('..'):
        return []
    if Path(stem).suffix:
        return [stem]
    return [stem + extension for extension in RESOLVE_EXTENSIONS] + \
           [posixpath.join(stem, 'index' + extension) for extension in RESOLVE_EXTENSIONS]


def _join(directory, specifier):
    """A project-relative resolved stem, or ``None`` when it leaves the project."""
    joined = posixpath.normpath(posixpath.join(directory, specifier)) if directory else posixpath.normpath(specifier)
    return None if joined.startswith(('..', '/')) else joined


class Resolver:
    """Bounded, project-local JS/TS module resolution over one indexed file set.

    The resolver reads every ``tsconfig.json`` and ``package.json`` in scope once, records a
    digest of what it read, and then answers per-specifier questions. It never reads a file
    outside the canonical project root and never follows a symlink.
    """

    def __init__(self, root, config_names, excluded=()):
        self.root = Path(root).resolve()
        self.names = sorted({name for name in config_names
                             if Path(name).name in CONFIG_NAMES
                             and not set(excluded).intersection(Path(name).parts)})
        self.files = set()
        self.notes = []
        self.configs = {}
        self.packages = {}
        self.config_sha256 = ''
        self._documents = {}
        self._charged = [0]
        self._load()

    def _document(self, name, label):
        """One link-free, memoised read of a configuration file in scope.

        Memoising keeps a manifest that several workspaces consult to one charged read, so the
        aggregate budget counts distinct configuration rather than how often it was asked for,
        and every configuration in scope passes the same protected-path and hardlink guard.
        """
        if name in self._documents:
            return self._documents[name]
        path = _canonical(self.root, name)
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('Module configuration must be a regular file: ' + name)
        value = _read_json(path, label, self._charged)
        self._documents[name] = value
        return value

    def _load(self):
        configs = [name for name in self.names if Path(name).name == 'tsconfig.json']
        manifests = [name for name in self.names if Path(name).name == 'package.json']
        if len(configs) > MAX_CONFIGS or len(manifests) > MAX_CONFIGS:
            raise ValueError('Too many module configurations in scope; narrow source_roots')
        for name in manifests:
            self._manifest(name)
        for name in configs:
            self._config(posixpath.dirname(name))
        self._workspaces(manifests)
        # A fingerprint of what was actually resolved, not of which file names exist: rewriting
        # an alias target leaves the name set untouched and moves every edge it decides.
        self.config_sha256 = digest(json.dumps(
            {'packages': self.packages, 'configs': self.configs, 'sources': self.names},
            sort_keys=True, separators=(',', ':')).encode())

    def _read_config(self, name, chain):
        """Read one ``tsconfig``, refusing escapes and cycles, returning merged options."""
        if name in chain:
            raise ValueError('Cyclic tsconfig extends chain: ' + ' -> '.join(chain + [name]))
        if len(chain) > MAX_EXTENDS:
            raise ValueError('tsconfig extends chain is too deep: ' + ' -> '.join(chain + [name]))
        value = self._document(name, 'tsconfig')
        merged = {'baseUrl': None, 'paths': {}}
        parents = value.get('extends')
        if isinstance(parents, str):
            parents = [parents]
        if isinstance(parents, list):
            for parent in parents:
                if not isinstance(parent, str) or not parent.strip():
                    raise ValueError('tsconfig extends entries must be strings: ' + name)
                if not (parent.startswith('.') or Path(parent).is_absolute() or '/' in parent or '\\' in parent):
                    self.notes.append('tsconfig-extends-external-package-not-applied')
                    continue
                target = _join(posixpath.dirname(name), parent)
                if target is None or not Path(target).suffix:
                    raise ValueError('tsconfig extends escapes the project: ' + parent)
                inherited = self._read_config(target if target.endswith('.json') else target + '.json',
                                              chain + [name])
                merged['baseUrl'] = merged['baseUrl'] or inherited['baseUrl']
                for key, targets in inherited['paths'].items():
                    merged['paths'].setdefault(key, targets)
        elif parents is not None:
            raise ValueError('tsconfig extends must be a string or array of strings: ' + name)
        options = value.get('compilerOptions')
        if options is not None and not isinstance(options, dict):
            raise ValueError('tsconfig compilerOptions must be an object: ' + name)
        options = options or {}
        base = options.get('baseUrl')
        if isinstance(base, str) and base:
            resolved = _join(posixpath.dirname(name), base)
            if resolved is None:
                raise ValueError('tsconfig baseUrl escapes the project: ' + base)
            merged['baseUrl'] = resolved
        paths = options.get('paths')
        if isinstance(paths, dict):
            for key, targets in paths.items():
                if not isinstance(key, str) or not isinstance(targets, list) or \
                        any(not isinstance(item, str) for item in targets):
                    raise ValueError('tsconfig paths must map patterns to string lists: ' + name)
                # A child's own declaration adds its targets to the inherited ones rather than
                # replacing them the way `tsc` replaces the whole `paths` map. Dropping the
                # parent's target could resolve an alias to the wrong file, so every declared
                # candidate is offered and more than one match is reported as ambiguous.
                merged['paths'][key] = merged['paths'].get(key, []) + [
                    target for target in targets if target not in merged['paths'].get(key, [])]
        return merged

    def _config(self, directory):
        """Load and cache the configuration that governs one directory."""
        if directory in self.configs:
            return self.configs[directory]
        name = posixpath.join(directory, 'tsconfig.json') if directory else 'tsconfig.json'
        merged = self._read_config(name, [])
        record = {'base': merged['baseUrl'] if merged['baseUrl'] is not None else (directory or None),
                  'paths': merged['paths']}
        self.configs[directory] = record
        return record

    def _nearest_config(self, seed):
        """The closest configuration at or above the importing file, bounded by the root."""
        directory = posixpath.dirname(seed)
        while True:
            name = posixpath.join(directory, 'tsconfig.json') if directory else 'tsconfig.json'
            if name in self.names:
                return self._config(directory)
            if directory == '':
                return None
            directory = posixpath.dirname(directory)

    def _manifest(self, name):
        """Register one workspace-local package by its declared name and entry points."""
        path = _canonical(self.root, name)
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            return None
        value = self._document(name, 'package.json')
        package = value.get('name')
        if not isinstance(package, str) or not package.strip() or len(self.packages) >= MAX_PACKAGES:
            return None
        exports = value.get('exports')
        if not isinstance(exports, (dict, list, str)):
            exports = None
        self.packages[package] = {
            'directory': posixpath.dirname(name), 'exports': exports,
            'main': value.get('main') if isinstance(value.get('main'), str) else None,
            'types': value.get('types') if isinstance(value.get('types'), str) else None}
        return self.packages[package]

    def _workspaces(self, manifests):
        """Map declared workspace package names to their project-local directories."""
        for name in manifests:
            directory = posixpath.dirname(name)
            patterns = self._declared_workspaces(directory)
            if not patterns:
                continue
            for pattern in patterns:
                if not pattern or Path(pattern).is_absolute() or '..' in Path(pattern).parts:
                    raise ValueError('Workspace patterns must be project-relative: ' + str(pattern))
                base = _join(directory, pattern.rstrip('/*'))
                for candidate in manifests:
                    folder = posixpath.dirname(candidate)
                    if folder == base or (pattern.endswith('*') and folder.startswith(base + '/')
                                          and '/' not in folder[len(base) + 1:]):
                        self._manifest(candidate)

    def _declared_workspaces(self, directory):
        name = posixpath.join(directory, 'package.json') if directory else 'package.json'
        if name not in self.names:
            return []
        path = _canonical(self.root, name)
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            return []
        declared = self._document(name, 'package.json').get('workspaces')
        if isinstance(declared, dict):
            declared = declared.get('packages')
        return [item for item in declared or [] if isinstance(item, str)]

    @staticmethod
    def _condition(value):
        """One ``exports`` target through the conditions a real bundler would consider."""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            for item in value:
                target = Resolver._condition(item)
                if target:
                    return target
            return None
        if isinstance(value, dict):
            for condition in CONDITIONS:
                if condition in value:
                    target = Resolver._condition(value[condition])
                    if target:
                        return target
        return None

    def _export_target(self, record, subpath):
        """Resolve one subpath through a package's declared ``exports`` field."""
        exports = record['exports']
        if exports is None:
            return None
        key = subpath or '.'
        if isinstance(exports, str):
            return exports if key == '.' else None
        if isinstance(exports, list):
            return None if key != '.' else self._condition(exports)
        if (not isinstance(exports, dict)
                or any(not isinstance(item, str) or not (item.startswith('./') or item in ('.', ''))
                       for item in exports)):
            # A root `exports` of bare condition names ("import", "require") declares no subpath
            # map at all; refusing it here falls back to the package entry point instead of
            # inventing a subpath. The bare `"."` key is the package root and is honoured.
            return None
        if key in exports:
            return self._condition(exports[key])
        best = None
        captured = None
        for pattern, value in exports.items():
            found = _wildcard(pattern, key)
            if found is not None and (best is None or len(pattern) > len(best)):
                best, captured = pattern, found
        target = self._condition(exports[best]) if best is not None else None
        return target.replace('*', captured) if isinstance(target, str) else None

    def _package(self, specifier):
        """Split a bare specifier into a known workspace package and its ``exports`` subpath.

        The subpath keeps the leading ``./`` an ``exports`` map is keyed by, so
        ``@app/core/util`` is looked up as ``./util`` rather than as a bare ``util``.
        """
        parts = specifier.split('/')
        names = [parts[0]] if not specifier.startswith('@') or len(parts) < 2 else \
            ['/'.join(parts[:2]), '/'.join(parts[:3]) if len(parts) > 2 else None]
        for name in names:
            if name and name in self.packages:
                remainder = specifier[len(name):].strip('/')
                return self.packages[name], './' + remainder if remainder else ''
        return None

    def _alias(self, seed, specifier):
        """``baseUrl``/``paths`` alias stems for one specifier, longest declared prefix first."""
        config = self._nearest_config(seed)
        if not config:
            return []
        matches = []
        for pattern, targets in config['paths'].items():
            if pattern.endswith('*'):
                captured = _wildcard(pattern, specifier)
                if captured is not None:
                    matches.append((len(pattern) - 1, captured, targets))
            elif pattern == specifier:
                matches.append((len(pattern), '', targets))
        matches.sort(key=lambda item: -item[0])
        stems = []
        for _, captured, targets in matches:
            for target in targets:
                if '*' in target:
                    stem = target.replace('*', captured)
                elif captured:
                    continue  # A literal target cannot satisfy a wildcard pattern.
                else:
                    stem = target
                joined = _join(config['base'] or '', stem)
                if joined is None:
                    # A declared target that leaves the project is refused, not ignored:
                    # silently dropping it would resolve the alias to the wrong file.
                    raise ValueError('Declared module alias escapes the project: ' + target)
                stems.append(joined)
        return stems

    def bind(self, files):
        """Fix the indexed file set this resolver may link to."""
        self.files = set(files)

    def resolve(self, seed, spec):
        """Indexed neighbours for one module specifier, with an honest status label."""
        specifier = spec['module']
        if not specifier:
            return [], 'unsupported'
        if spec.get('kind') == 'dynamic':
            found, status = self._resolve_static(seed, specifier)
            return found, status + '+dynamic'
        return self._resolve_static(seed, specifier)

    def _resolve_static(self, seed, specifier):
        if specifier.startswith('/'):
            return [], 'absolute-specifier-refused'
        if specifier.startswith('.'):
            base = _join(posixpath.dirname(seed), specifier)
            found = self._indexed(_candidates(base or ''))
            return found, 'resolved' if found else 'unresolved'
        found = self._indexed([candidate for stem in self._alias(seed, specifier)
                               for candidate in _candidates(stem)])
        if len(found) > 1:
            self.notes.append('ts-alias-matched-multiple-project-files:' + specifier)
            return found, 'ambiguous'
        if found:
            return found, 'resolved'
        package = self._package(specifier)
        if package is None:
            return [], 'external'
        record, subpath = package
        target = self._export_target(record, subpath)
        if target is not None:
            base = _join(record['directory'], target)
        elif subpath:
            base = _join(record['directory'], subpath)
        else:
            base = _join(record['directory'], record['types'] or record['main'] or 'index')
        found = self._indexed(_candidates(base or ''))
        return found, 'resolved' if found else 'workspace-package-not-indexed'

    def _indexed(self, candidates):
        return sorted({candidate for candidate in candidates if candidate in self.files})