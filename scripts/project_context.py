"""Frozen per-task context generations with hash-validated code ranges.

A generation is immutable evidence for one (project ID, checkout ID, root, task ID)
scope. Ranges are cache keys over project ID, checkout ID, file hash, line range,
policy version and parser version, so a changed file can never keep a stale line
reference. Managed model calls cannot fetch code, so only explicitly declared
source bodies are embedded here, and required content is never silently dropped.
"""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import workflow as w

SCHEMA_VERSION = 1
POLICY_VERSION = 'project-context-1'
MAX_BODIES = 32
MAX_LESSONS = 24
MAX_RANGES = 128
MAX_RANGE_RECORDS = 64
MAX_RANGE_SYMBOLS = 12
MAX_INDEXED_NAMES = 128
OPTIONAL_DETAIL = {'ranges': 'suggested read ranges', 'tests': 'related test hints',
                   'neighbours': 'dependency neighbour hints'}
RANGES_DETAIL = ('suggested read ranges outside their own byte allowance and record cap; '
                 'the context ceiling is not a target for optional hints')
VOLATILE = ('created_at', 'telemetry')
NON_SEMANTIC = ('sha256', 'semantic_sha256', 'bytes', 'generation')
LABELS = {
    'en': {'rules': 'Governing rules (complete)', 'criteria': 'Acceptance criteria (complete)',
           'navigation': 'Navigation index (partial graph; read real files)',
           'lessons': 'Verified project lessons', 'ranges': 'Suggested read ranges (validate hashes)',
           'bodies': 'Declared source bodies', 'omissions': 'Recorded omissions',
           'stale': 'Stale reference', 'generated': 'Generated'},
    'ar': {'rules': 'القواعد الحاكمة (كاملة)', 'criteria': 'معايير القبول (كاملة)',
           'navigation': 'فهرس التنقل (رسم جزئي؛ اقرأ الملفات الحقيقية)',
           'lessons': 'دروس المشروع المتحقق منها', 'ranges': 'نطاقات قراءة مقترحة (تحقق من البصمة)',
           'bodies': 'محتوى المصادر المصرح به', 'omissions': 'حذف مسجّل',
           'stale': 'مرجع منتهٍ', 'generated': 'أُنشئ'},
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def semantic(value):
    """Strip nondeterministic telemetry so unchanged entry reuses its generation."""
    if isinstance(value, dict):
        return {key: semantic(item) for key, item in value.items() if key not in VOLATILE}
    if isinstance(value, list):
        return [semantic(item) for item in value]
    return value


def semantic_digest(context):
    """Fingerprint the semantic content only.

    The generation counter, the serialized size and every telemetry-derived field are
    bookkeeping, not task evidence: including them made an unchanged re-entry miss the
    stored generation and increment forever once any earlier generation had been written.
    """
    return w.digest(canonical(semantic({key: item for key, item in context.items()
                                        if key not in NON_SEMANTIC})).encode())


def seal(context):
    """Fill the final fields so the recorded size is the exact serialized payload on disk."""
    for _ in range(6):
        context['semantic_sha256'] = semantic_digest(context)
        context['sha256'] = w.digest(canonical({key: item for key, item in context.items()
                                                if key != 'sha256'}).encode())
        total = len((canonical(context) + '\n').encode())
        if total == context.get('bytes'):
            return context
        context['bytes'] = total
    raise ValueError('Frozen context size did not converge; lower the declared content')


def payload_bytes(context):
    return len((canonical(context) + '\n').encode())


def config_facts(root, config):
    import repo_map
    return {'sha256': w.digest(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()),
            'source_roots': list(config.get('source_roots') or []),
            'exclude': list(config.get('exclude') or []),
            'budgets': dict(config.get('budgets') or {}),
            'policy': dict(config.get('policy') or {}),
            'language': config.get('language'),
            'map_parser_versions': dict(repo_map.PARSER_VERSIONS),
            'map_generation': repo_map.GENERATION_VERSION,
            'context_policy_version': POLICY_VERSION}


def context_path(root, task_id):
    return w.safe_path(root, '.crewloom/context/' + task_id + '.json', internal=True)


def related_tests(value, seeds):
    """Name test files that mention a seed module or one of its symbols; a hint, not a graph."""
    files = value['files']
    tokens = set()
    for seed in seeds:
        tokens.add(Path(seed).stem)
        tokens.update(symbol['name'] for symbol in files.get(seed, {}).get('symbols', []))
    found = []
    for name, entry in files.items():
        parts = Path(name).parts
        if 'test' not in Path(name).stem.lower() and not any(part in ('tests', 'test') for part in parts):
            continue
        text = name + ' ' + ' '.join(symbol['name'] for symbol in entry.get('symbols', []))
        if tokens & set(re.findall(r'\w{3,}', text.casefold())):
            found.append(name)
    return sorted(found)


def ordered_paths(paths):
    """Deterministic, de-duplicated paths; the caller controls priority order."""
    seen = set()
    ordered = []
    for name in paths:
        relative = Path(name).as_posix()
        if not relative or relative in seen:
            continue
        seen.add(relative)
        ordered.append(relative)
    return ordered


def record_cost(item):
    """Exact serialized cost of appending one record to a canonical JSON array."""
    return len(canonical(item).encode()) + 1


def bounded_records(items, room, required=0, limit=None):
    """Keep as many optional records as the remaining serialized room allows.

    The first `required` items are always kept, so declared sources and seed navigation are
    never traded away for optional hints. `limit` bounds the total record count as well:
    a record count multiplied by a generous ceiling is not a bounded hint, and the caller
    records what it had to leave out.
    """
    kept = []
    used = 0
    for position, item in enumerate(items):
        if limit is not None and len(kept) >= limit:
            break
        cost = record_cost(item)
        if position < required or used + cost <= room:
            kept.append(item)
            used += cost
    return kept, len(items) - len(kept)


def range_budget(config):
    """Optional range allowance: explicit when configured, otherwise the map allocation."""
    budgets = config.get('budgets') or {}
    declared = budgets.get('range_bytes')
    return declared if isinstance(declared, int) else budgets['map_bytes']


def ranges_for(root, value, paths):
    """Bind every suggested range to the exact file hash that made it valid.

    Two files with identical content and identical symbols still resolve separately: the
    normalized project-relative path and the scope are part of the cache key, so a key can
    never be spent on a different path.
    """
    ranges = []
    for name in ordered_paths(paths)[:MAX_RANGES]:
        entry = value['files'].get(name)
        if not entry:
            continue
        relative = Path(name).as_posix()
        fingerprint = w.digest(w.safe_path(root, relative).read_bytes())
        for symbol in entry.get('symbols', [])[:MAX_RANGE_SYMBOLS]:
            ranges.append({'path': relative, 'start': symbol['line'], 'end': symbol['end'] or symbol['line'],
                           'kind': symbol['kind'], 'name': symbol['name'], 'sha256': fingerprint,
                           'parser': entry['parser'], 'parser_version': entry.get('parser_version'),
                           'policy_version': POLICY_VERSION,
                           'cache_key': w.digest(canonical({'project_id': value.get('project_id'),
                                                           'checkout_id': value.get('checkout_id'),
                                                           'path': relative,
                                                           'sha256': fingerprint, 'start': symbol['line'],
                                                           'end': symbol['end'] or symbol['line'],
                                                           'policy': POLICY_VERSION,
                                                           'parser': entry.get('parser_version')}).encode())})
    return ranges


def bounded_lessons(items, budget):
    """Keep verified lessons inside their exact serialized byte budget.

    A selector that only counts records cannot see how large one remedy is, so the final
    list is measured as it is stored and the surplus is recorded instead of truncated.
    """
    kept, dropped = bounded_records(items, max(0, budget - 1))
    while kept and len(canonical(kept).encode()) > budget:
        kept.pop()
    return kept, len(items) - len(kept)


def lesson_selection(root, config, seeds, tokens):
    import project_lessons
    # A verified remedy whose declared source, recorded artifact or policy changed is stale
    # evidence. Revalidating here means entry can neither deliver it nor keep claiming it is
    # verified, instead of waiting for an operator to run the revalidation command by hand.
    policy = Path(root) / 'crewloom.project.json'
    project_lessons.revalidate(root, w.digest(policy.read_bytes()) if policy.is_file() else None)
    limit = min(MAX_LESSONS, max(0, config['budgets']['lesson_budget_bytes'] // 256))
    return project_lessons.select(root, seeds, tokens, limit)


def snapshot(root, binding, task_id, role, config, criteria, seeds, language=None, declared=(),
             criteria_path=None):
    """Build one bounded context generation; required content must fit or the task fails."""
    import repo_map
    root = Path(root).resolve()
    language = language or config.get('language', 'en')
    if language not in LABELS:
        raise ValueError('Task context language must be en or ar')
    setup = w.project_role(root, role)
    if not setup['ready']:
        raise ValueError('Project context needs one installed role: ' + str(setup.get('error', '')))
    guide = Path(setup['guide'])
    budget = config['budgets']['context_bytes']
    rules = []
    for path in (guide, root / 'AGENTS.md', root / 'CLAUDE.md'):
        if not path.is_file():
            continue
        data = path.read_bytes()
        rules.append({'path': str(path.relative_to(root)), 'sha256': w.digest(data),
                      'bytes': len(data), 'text': data.decode('utf-8', 'replace')})
    rules_bytes = sum(item['bytes'] for item in rules)
    criteria_bytes = sum(len(line.encode()) for line in criteria)
    criteria_file = None
    if criteria_path:
        path = w.safe_path(root, criteria_path)
        if not path.is_file():
            raise ValueError('Acceptance criteria file is missing: ' + criteria_path)
        criteria_file = {'path': criteria_path, 'sha256': w.digest(path.read_bytes())}
    if rules_bytes + criteria_bytes > budget:
        raise ValueError('Governing rules and acceptance criteria exceed context_bytes; raise the budget explicitly')
    bodies = []
    declared_bytes = 0
    for name in list(declared)[:MAX_BODIES + 1]:
        path = w.safe_path(root, name)
        if not path.is_file():
            raise ValueError('Declared source body is missing: ' + name)
        if path.stat().st_nlink != 1 or path.is_symlink():
            raise ValueError('Declared source body must be a regular file without links: ' + name)
        # Refuse on the declared size: an oversized required body must never be read into
        # memory to discover it cannot fit.
        if path.stat().st_size > budget - rules_bytes - criteria_bytes - declared_bytes:
            raise ValueError('Declared source bodies exceed context_bytes; narrow the task or '
                             'raise the budget explicitly')
        data = path.read_bytes()
        declared_bytes += len(data)
        bodies.append({'path': name, 'sha256': w.digest(data), 'bytes': len(data),
                       'text': data.decode('utf-8', 'replace')})
    if len(list(declared)) > MAX_BODIES:
        raise ValueError('Too many declared source bodies; the context cannot silently drop required input')
    value, stats = repo_map.build(root, config=config)
    seeds = [name for name in seeds if name]
    remaining = budget - rules_bytes - criteria_bytes - declared_bytes
    if remaining < 2048:
        raise ValueError('Rules, criteria and declared sources leave no room for navigation; raise context_bytes')
    map_budget = max(1024, min(config['budgets']['map_bytes'], remaining // 2))
    navigation, selection = repo_map.render(value, ' '.join(list(seeds) + list(criteria)), map_budget, seeds)
    omitted = []
    if selection['omitted_files']:
        omitted.append({'kind': 'map-files', 'count': selection['omitted_files'],
                        'detail': 'navigation index omitted files outside the byte budget'})
    if selection['missing_seed_files']:
        omitted.append({'kind': 'map-seeds', 'count': len(selection['missing_seed_files']),
                        'detail': 'seed paths are not indexed in this checkout'})
    if selection['truncated_seed_files']:
        omitted.append({'kind': 'map-seed-symbols', 'count': len(selection['truncated_seed_files']),
                        'detail': 'seed symbol lists exceeded the map budget; the file itself is present'})
    if not selection['graph_complete']:
        omitted.append({'kind': 'dependency-resolution', 'count': len(value['incomplete_files']),
                        'detail': 'package, alias and unsupported syntax resolution is a deferred adapter'})
    if len(value['files']) > MAX_INDEXED_NAMES:
        omitted.append({'kind': 'indexed-names', 'count': len(value['files']),
                        'detail': 'the generation keeps a digest of the indexed file set plus a bounded sample'})
    tokens = set(re.findall(r'\w{3,}', (' '.join(seeds) + ' ' + ' '.join(criteria)).casefold()))
    lessons = lesson_selection(root, config, seeds, tokens)
    kept_lessons, dropped_lessons = bounded_lessons(lessons['lessons'],
                                                    config['budgets']['lesson_budget_bytes'])
    omitted_lessons = lessons['omitted'] + dropped_lessons
    if omitted_lessons:
        omitted.append({'kind': 'lessons', 'count': omitted_lessons,
                        'detail': 'verified lessons outside the byte budget were omitted'})
    context = {'schema_version': SCHEMA_VERSION, 'generation': 1, 'created_at': now(),
               'scope': {'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
                         'project_root': str(root), 'task_id': task_id, 'role': role, 'language': language},
               'policy': {'mode': config['policy']['mode'], 'managed_lifecycle': config['policy']['managed_lifecycle'],
                          'version': POLICY_VERSION},
               'rules': rules, 'criteria': list(criteria), 'criteria_file': criteria_file,
               'configuration': config_facts(root, config),
               'navigation': {'text': navigation, 'stats': selection},
               'map': {'generation': stats['generation'], 'files': stats['files'],
                       'scan_bytes': stats['scan_bytes'], 'branch': stats['branch'], 'head': stats['head'],
                       'graph_complete': stats['graph_complete'], 'source_roots': config.get('source_roots'),
                       'indexed_names': sorted(value['files'])[:MAX_INDEXED_NAMES],
                       'indexed_names_count': len(value['files']),
                       'indexed_names_sha256': w.digest(canonical(sorted(value['files'])).encode()),
                       'indexed_names_truncated': len(value['files']) > MAX_INDEXED_NAMES,
                       'project_id': value.get('project_id'), 'checkout_id': value.get('checkout_id')},
               'telemetry': {'parsed': stats['parsed'], 'reused': stats['reused'],
                             'duration_ms': stats['duration_ms'], 'generated_at': now()},
               'ranges': [], 'tests': [], 'neighbours': [], 'lessons': kept_lessons,
               'negative_evidence': lessons['negative_evidence_count'], 'bodies': bodies, 'omissions': omitted,
               'provider': {'usage_available': False, 'cached_tokens_available': False,
                            'note': 'provider usage is recorded only when the provider reports it'}}
    # Required content is sealed first; optional hints then take only the room that is left.
    context['bytes'] = 0
    context = seal(context)
    if context['bytes'] > budget:
        raise ValueError('Rules, criteria and declared sources leave no room for a complete generation; '
                         'raise context_bytes or narrow the task')
    room = budget - context['bytes']
    tests = related_tests(value, seeds)
    neighbours = sorted({target for seed in seeds for target in value['files'].get(seed, {}).get('neighbours', [])})
    ranges = ranges_for(root, value, ordered_paths(list(seeds) + list(tests) + list(neighbours)))
    seed_set = {Path(name).as_posix() for name in seeds}
    seed_ranges = sum(1 for item in ranges if item['path'] in seed_set)
    context['tests'], dropped_tests = bounded_records(tests, room)
    room -= sum(record_cost(item) for item in context['tests'])
    # Optional ranges carry their own allowance and record cap. Spending whatever the global
    # required-body ceiling leaves over would fill a large context with unrelated symbols and
    # starve the workflow that has to read the whole frozen snapshot back.
    range_room = min(room, range_budget(config))
    context['ranges'], dropped_ranges = bounded_records(ranges, range_room, required=seed_ranges,
                                                        limit=max(MAX_RANGE_RECORDS, seed_ranges))
    room -= sum(record_cost(item) for item in context['ranges'])
    context['neighbours'], dropped_neighbours = bounded_records(neighbours, room)
    dropped = {'tests': dropped_tests, 'ranges': dropped_ranges, 'neighbours': dropped_neighbours}
    context = seal(context)
    while context['bytes'] > budget:
        # Only the recorded size of its own value can push this over; give back optional
        # records instead of required rules, criteria or declared source bodies.
        victim = next((key for key in ('ranges', 'neighbours', 'tests') if context[key]), None)
        if victim is None:
            break
        context[victim].pop()
        dropped[victim] += 1
        context = seal(context)
    for kind, count in sorted(dropped.items()):
        if count:
            omitted.append({'kind': kind, 'count': count,
                            'detail': RANGES_DETAIL if kind == 'ranges'
                            else OPTIONAL_DETAIL[kind] + ' outside the remaining byte budget'})
    context = seal(context)
    if context['bytes'] > budget:
        navigation, selection = repo_map.render(value, ' '.join(list(seeds) + list(criteria)),
                                                max(1024, budget - (context['bytes'] - selection['map_bytes'])),
                                                seeds)
        context = dict(context, navigation={'text': navigation, 'stats': selection})
        context['omissions'] = list(omitted) + [
            {'kind': 'navigation-trim', 'count': selection['omitted_files'],
             'detail': 'navigation re-rendered at the reduced byte budget'}]
        context = seal(context)
    if context['bytes'] > budget:
        raise ValueError('Frozen context needs ' + str(context['bytes']) + ' bytes but context_bytes is '
                         + str(budget) + '; raise the budget or narrow the task')
    return context


def history_path(root, task_id, generation):
    return w.safe_path(root, '.crewloom/context/history/' + task_id + '/generation-' + str(generation) + '.json',
                       internal=True)


def keep_history(root, task_id, generation, context):
    """Archive one immutable generation once; an existing copy is never overwritten."""
    keep = history_path(root, task_id, generation)
    if keep.is_file():
        return keep
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text(canonical(context) + '\n', encoding='utf-8')
    return keep


def freeze(root, context):
    """Write one immutable generation, keep its history, and reuse it when nothing semantic changed."""
    task_id = context['scope']['task_id']
    path = context_path(root, task_id)
    if path.is_file():
        existing = load(root, {'task_id': task_id}, verify_hashes=False, allow_invalidated=True)
        stored = existing.get('scope') or {}
        for field in ('project_id', 'checkout_id'):
            if stored.get(field) != context['scope'][field]:
                raise ValueError('Frozen context for this task belongs to another project or checkout: ' + field)
        if not existing.get('invalidated') and existing.get('semantic_sha256') == context['semantic_sha256']:
            return existing, False
        keep_history(root, task_id, existing.get('generation', 1), existing)
        context = seal(dict(context, generation=existing.get('generation', 1) + 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(canonical(context) + '\n', encoding='utf-8')
    temporary.replace(path)
    return context, True


def _validated(root, context, expected):
    """Identity, fingerprint and size checks that every generation file must pass."""
    if not isinstance(context, dict) or context.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Malformed frozen context schema')
    stored = context.get('scope') or {}
    for field in ('project_id', 'checkout_id', 'project_root', 'task_id'):
        wanted = expected.get(field) if isinstance(expected, dict) else None
        if wanted is not None and stored.get(field) != wanted:
            raise ValueError('Frozen context belongs to another project, checkout or task: ' + field)
    if stored.get('project_root') != str(root):
        raise ValueError('Frozen context belongs to another project root')
    if w.digest(canonical({key: item for key, item in context.items() if key != 'sha256'}).encode()) != context.get('sha256'):
        raise ValueError('Frozen context fingerprint does not match its content')
    if semantic_digest(context) != context.get('semantic_sha256'):
        raise ValueError('Frozen context semantic fingerprint does not match its content')
    if payload_bytes(context) != context.get('bytes'):
        raise ValueError('Recorded context size does not match the stored payload')
    return context


def load(root, scope, verify_hashes=True, allow_invalidated=False):
    """Load one generation and reject a scope that belongs to another project or checkout."""
    root = Path(root).resolve()
    task_id = scope['task_id'] if isinstance(scope, dict) else scope
    path = context_path(root, task_id)
    if not path.is_file():
        raise ValueError('No frozen context for task: ' + str(task_id))
    if path.is_symlink() or path.stat().st_nlink != 1:
        raise ValueError('Frozen context must be a regular file without hardlinks')
    try:
        context = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('Malformed frozen context: ' + str(exc))
    _validated(root, context, scope if isinstance(scope, dict) else {})
    if context.get('invalidated') and not allow_invalidated:
        raise ValueError('Frozen context was invalidated: ' + context['invalidated'].get('reason'))
    if verify_hashes and changed_files(root, context):
        raise ValueError('Frozen context is stale; rebuild before use: '
                         + ', '.join(changed_files(root, context)[:8]))
    return context


def archived_generation(root, task_id, generation):
    """Load one exact immutable generation by number, from the archive or the current file.

    Managed evidence names the generation a call consumed instead of guessing which archived
    context happens to share its declared sources, so a reused step is verified against the
    very bytes it saw rather than the newest or the oldest plausible candidate. Freshness is
    deliberately not rechecked: this is historical evidence, not a publication gate.
    """
    root = Path(root).resolve()
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise ValueError('Model step evidence must name one exact context generation')
    expected = {'task_id': task_id, 'project_root': str(root)}
    for path in (history_path(root, task_id, generation), context_path(root, task_id)):
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            continue
        try:
            context = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(context, dict) or context.get('generation') != generation:
            continue
        return _validated(root, context, expected)
    raise ValueError('No immutable project context generation ' + str(generation) + ' for task: ' + str(task_id))


def changed_files(root, context):
    changed = []
    for item in list(context.get('rules', [])) + list(context.get('bodies', [])):
        path = w.safe_path(root, item['path'])
        if not path.is_file() or w.digest(path.read_bytes()) != item['sha256']:
            changed.append(item['path'])
    criteria_file = context.get('criteria_file')
    if criteria_file:
        path = w.safe_path(root, criteria_file['path'])
        if not path.is_file() or w.digest(path.read_bytes()) != criteria_file['sha256']:
            changed.append(criteria_file['path'])
    if not criteria_file and context.get('criteria'):
        changed.append('criteria: recorded without a source file')
    checked = set()
    for item in context.get('ranges', []):
        name = item['path']
        if name in checked:
            continue
        checked.add(name)
        path = w.safe_path(root, name)
        if not path.is_file() or w.digest(path.read_bytes()) != item['sha256']:
            changed.append(name)
    changed.extend(configuration_drift(root, context))
    changed.extend(index_drift(root, context))
    return sorted({item for item in changed if item})


def configuration_drift(root, context):
    recorded = context.get('configuration') or {}
    import project_binding as pb
    config, _ = pb.load_config(root)
    if config is None:
        return ['crewloom.project.json: removed after freezing']
    current = config_facts(root, config)
    return ['crewloom.project.json: ' + key for key in sorted(recorded)
            if key in current and recorded[key] != current[key]]


def index_drift(root, context):
    """A branch switch or a create/delete/rename inside the indexed scope invalidates the snapshot.

    The candidate inventory is recomputed with the same scope, exclusions and skips the index
    itself uses, so a file outside the configured scope never invalidates a frozen generation.
    """
    import repo_map
    import project_binding as pb
    recorded = context.get('map') or {}
    try:
        root = Path(root).resolve()
        state = repo_map.git_state(root)
        config, _ = pb.load_config(root)
        source_roots, excluded = repo_map.scope_for(root, config)
        current = repo_map.inventory(root, state, source_roots, excluded)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return ['index: ' + str(exc)]
    drift = []
    if state['branch'] != recorded.get('branch'):
        drift.append('branch: ' + str(recorded.get('branch')) + ' -> ' + str(state['branch']))
    if state['head'] != recorded.get('head'):
        drift.append('head: index generation recorded a different commit')
    if recorded.get('indexed_names_sha256'):
        # The full name list is not stored; its digest still detects every in-scope added,
        # removed or renamed path, and the bounded sample explains the difference.
        if w.digest(canonical(current).encode()) != recorded['indexed_names_sha256']:
            drift.extend(_index_detail(set(recorded.get('indexed_names') or []), set(current)))
        return drift
    indexed = set(recorded.get('indexed_names') or [])
    if indexed:
        added = sorted(set(current) - indexed)
        removed = sorted(indexed - set(current))
        if added:
            drift.append('index: ' + str(len(added)) + ' added file(s)')
        if removed:
            drift.append('index: ' + str(len(removed)) + ' removed file(s)')
    return drift


def _index_detail(recorded, current):
    added = len(current - recorded)
    removed = len(recorded - current)
    detail = ['index: the indexed file set changed']
    if added:
        detail[0] += ' (' + str(added) + ' added)'
    if removed:
        detail[0] += ' (' + str(removed) + ' removed)'
    return detail


def resolve_range(root, context, cache_key, path, start, end):
    """Return code lines for a cited range only when its evidence still matches."""
    if (context.get('scope') or {}).get('project_root') != str(Path(root).resolve()):
        raise ValueError('Range evidence belongs to another project root')
    item = next((entry for entry in context.get('ranges', []) if entry['cache_key'] == cache_key), None)
    if item is None:
        raise ValueError('Unknown range cache key; rebuild the context instead of guessing lines')
    if item['path'] != path or item['start'] != start or item['end'] != end:
        raise ValueError('Range does not match the frozen generation')
    target = w.safe_path(root, path)
    if not target.is_file() or w.digest(target.read_bytes()) != item['sha256']:
        raise ValueError('Stale line reference: the file changed after the context was frozen')
    lines = target.read_text(encoding='utf-8', errors='replace').splitlines()
    if end > len(lines):
        raise ValueError('Stale line reference: the file is shorter than the frozen range')
    return '\n'.join(lines[start - 1:end])


def bodies(root, context, requested=None):
    """Only explicitly declared source bodies leave the trusted coordinator for managed calls."""
    available = {item['path']: item for item in context.get('bodies', [])}
    names = list(requested) if requested else sorted(available)
    return {name: available[name] for name in names if name in available}


def require_fresh(root, binding, task_id):
    """Enforced publication gate: obsolete evidence blocks managed output."""
    return load(root, {'task_id': task_id, 'project_id': binding['project_id'],
                       'checkout_id': binding['checkout_id'], 'project_root': str(Path(root).resolve())})


def invalidate(root, task_id, reason):
    """Mark a generation stale instead of deleting the record of what was believed.

    The immutable generation is archived before the invalidation marker is added, so the
    content a managed call actually consumed stays readable under its original fingerprint.
    """
    path = context_path(root, task_id)
    if not path.is_file():
        return None
    context = json.loads(path.read_text(encoding='utf-8'))
    if context.get('invalidated'):
        return context['invalidated']
    keep_history(root, task_id, context.get('generation', 1), context)
    context['invalidated'] = {'at': now(), 'reason': str(reason)[:200]}
    context = seal(context)
    path.write_text(canonical(context) + '\n', encoding='utf-8')
    return context['invalidated']
