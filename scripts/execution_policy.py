"""Trusted artifact broker: containers see declared files, never the project mount.

A step publishes its declared outputs as one group. The group is validated and staged whole
before the first destination is touched, journalled with a backup of every destination it will
replace, and then applied under the project lock, which is held for the whole publication and
its recovery. A failure part-way through is rolled back to the recorded original content and
mode, or removes only the files that attempt itself created, and only after every journal record
is proven restorable. A writer that is killed part-way through leaves a journal that the next
managed publication, project entry or workflow run reconciles before it writes anything of its
own.

A filesystem cannot make several files appear at once, so this is deliberately not an instant
multi-file atomic change. Both committed and reverted groups leave a bounded receipt, and
anything this protocol cannot prove it created is reported for manual reconciliation rather
than deleted.
"""
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import uuid

import crewloom_resources as resources

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_ARTIFACTS = 128
# Backups copy whatever a destination already held, so the group that may be rolled back is
# bounded too rather than being limited only by the size of what it writes.
MAX_BACKUP_BYTES = 16 * 1024 * 1024
MAX_RECEIPTS = 64
MAX_PENDING = 8
TRANSACTIONS = '.crewloom/transactions'
JOURNAL_VERSION = 1
# A whole group is present under `.crewloom` before the first destination write, so an
# interrupted writer leaves every byte it intended to publish on disk for recovery.
BACKUP = 'backup'
PAYLOAD = 'payload'
COMMITTED = 'committed'
# A group that failed and was fully reverted is finished, not pending: its journal is released
# so it is never reconciled twice, and a receipt keeps the failed attempt as history.
ROLLED_BACK = 'rolled-back'
# Everything a transaction folder of this protocol may contain, including the fixed staging
# file one record is renamed through. Anything else inside one is left exactly where it is and
# reported, so recovery never deletes a file it cannot prove it created, and never walks out of
# the folder it staged.
STAGED = ('journal.json', BACKUP, PAYLOAD)
TEMPORARY = '.tmp'
# One staged copy is named by the index of the destination it belongs to, and nothing else, so a
# transaction folder can be proved owned by name from its own journal instead of by the shape of
# whatever happens to be inside it.
STAGED_SUFFIX = '.bin'
STAGED_NAME = re.compile(r'([0-9]{1,6})' + re.escape(STAGED_SUFFIX))
# A journal is a bounded record: its fixed fields, at most MAX_ARTIFACTS destinations with two
# fingerprints and one declared path each, and the same many input fingerprints. That is far
# below this even for the longest ordinary project paths, so a larger file is not a record this
# protocol wrote, and reading it whole before checking would be an unbounded allocation inside
# the recovery path.
MAX_JOURNAL_BYTES = 1024 * 1024
# A receipt is written through the same fixed staging name; a leftover there is a record that
# was never renamed into place, so it is dropped with the oldest receipts rather than kept.
RECEIPT_SUFFIXES = ('.json', '.json' + TEMPORARY)
# Every field one destination record must carry before a rollback is allowed to act on it.
ENTRY_KEYS = ('index', 'path', 'state', 'existed', 'mode', 'bytes',
              'original_sha256', 'new_sha256')
ENTRY_STATES = ('pending', 'replacing', 'replaced')
# The original byte count of a destination is recorded beside its original digest so recovery can
# reject a truncated or padded backup before reading it, rather than only after hashing it. It is
# a recorded value, not an extra required key: an older journal that never wrote one is still
# checked by the digest, which is what actually decides whether the staged bytes are the original.
ORIGINAL_BYTES = 'original_bytes'
# Every field a whole journal must carry before any of its records is acted on.
JOURNAL_KEYS = ('schema_version', 'transaction', 'project_root', 'created_at', 'state',
                'inputs', 'created_parents', 'entries')
# The only state that still owns destinations. `committed` and `rolled-back` are finished
# histories that keep staged bytes but own nothing, so they are released rather than undone.
JOURNAL_STATES = ('prepared',)
JOURNAL_FINGERPRINT = re.compile(r'[0-9a-f]{64}$')
MAX_PARENTS = 256


def trusted_roots():
    """Directories a declared artifact destination may never touch.

    The distribution root covers a source checkout. In an installed wheel the trusted CLI
    modules sit beside the packaged role data rather than inside it, so the module root is
    protected separately: a project that contains its own copy of the runtime still cannot
    have that copy rewritten by a step.

    The roots are returned as the caller declared them, and containment is decided by physical
    directory identity as well as lexically, so a case or normalization spelling of a trusted
    directory reaches the same refusal.
    """
    import workflow as w
    roots = [w.LIBRARY, *resources.installed_roots()]
    return {Path(root).resolve() for root in roots if Path(root) is not None}


def destinations(root, outputs):
    """Validate one declared output group as a whole, before the first destination is touched.

    The group is checked as a group because the failure this exists to stop is two declared
    outputs that are one file: a case or normalization spelling the host filesystem resolves
    identically to another. Names are therefore folded before they are compared, so a
    collision is refused even when neither file exists yet and nothing can be probed, and the
    same rule holds on a genuinely case-sensitive filesystem where the two spellings really
    would have been two files. Existing destinations are additionally compared by device and
    inode, so a physical alias is refused even when no spelling rule explains it.
    """
    import workflow as w
    if len(outputs)>MAX_ARTIFACTS:raise ValueError('Too many output artifacts')
    trusted=trusted_roots()
    found={};keys={};identities=set()
    for relative in outputs:
        current=root
        for part in Path(relative).parts:
            current=current/part
            if current.is_symlink():raise ValueError('Output paths may not use symlinks')
        path=w.declared_path(root,relative)
        if w.inside(path,trusted):
            raise ValueError('Trusted Crewloom runtime is read-only; use a separate project/worktree')
        if path in found.values():raise ValueError('Output aliases are forbidden')
        key=w.path_key(path.relative_to(root))
        if key in keys:
            raise ValueError('Output names collide on a case-insensitive or normalizing '
                             'filesystem: '+str(keys[key])+' and '+str(relative))
        if path.exists():
            info=path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                raise ValueError('Output must be a regular file without hardlinks')
            identity=(info.st_dev,info.st_ino)
            if identity in identities:raise ValueError('Output aliases are forbidden')
            identities.add(identity)
        keys[key]=relative
        found[relative]=path
    return found


def _internal(root, *parts):
    """One runtime-state path under `.crewloom`, refusing links and escapes."""
    import workflow as w
    return w.safe_path(Path(root).resolve(), '/'.join((TRANSACTIONS,) + parts), internal=True)


def _timestamp():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _sync(folder):
    """Flush a directory entry, where the platform supports it.

    Best effort by design: some filesystems refuse `fsync` on a directory handle, and a
    publication that has already been journalled is still recoverable there.
    """
    try:
        handle = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def _staging(path):
    """The deterministic sibling a record is written through before it is renamed into place.

    The name is fixed rather than anonymous so that a writer killed mid-write leaves one
    recognisable file that the next write of the same record simply truncates, and that a
    transaction folder can be released without deleting something it cannot prove it created.
    Only the root lock serialises these writes, and it is held for every one of them.
    """
    return path.parent / ('.' + path.name + TEMPORARY)


def _write_record(path, value):
    """Replace one internal JSON record atomically and durably."""
    temporary = _staging(path)
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    _sync(path.parent)


def _staged_name(index):
    """The one staged file name a destination index is stored in, inside either stage."""
    return str(index) + STAGED_SUFFIX


def _valid_index(value):
    """Whether this value is one destination index a staged file can be named by."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < MAX_ARTIFACTS


def _record_bytes(path, limit, label):
    """The bytes of one internal record, read only after its own metadata proves it safe to read.

    A journal lives inside the project, so it can be corrupt, hostile or simply enormous, and
    recovery is the one path that must work on whatever it finds. Reading it into memory before
    checking anything would turn that into an unbounded allocation, so the file is inspected
    first: it must be a regular file with one link, and within the record budget. The read
    itself stops one byte past that budget, so a file that grew after the check is still
    refused rather than parsed.
    """
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(label + ' is not a private regular file: ' + str(path))
    if info.st_size > limit:
        raise ValueError(label + ' exceeds the record budget: ' + str(path))
    with open(path, 'rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(label + ' exceeds the record budget: ' + str(path))
    return data


def _record_value(path, label):
    """One parsed internal record, bounded before it is read and before it is parsed."""
    data = _record_bytes(path, MAX_JOURNAL_BYTES, label)
    return json.loads(data.decode('utf-8'))


def _fingerprint(target):
    """The current bytes of a destination, or ``None`` when it does not exist."""
    import workflow as w
    if target.is_symlink() or not target.exists():
        return None
    if not target.is_file():
        return 'not-a-regular-file'
    return w.digest(target.read_bytes())


def _pending(root):
    """Every transaction folder that was prepared but not yet committed, oldest first."""
    folder = _internal(root, 'pending')
    if not folder.is_dir():
        return []
    if folder.is_symlink():
        raise ValueError('Publication journal directory may not be a symlink: ' + str(folder))
    found = []
    for item in sorted(folder.iterdir(), key=lambda item: item.name):
        if item.is_symlink():
            # This protocol only ever creates a real folder per transaction. A link at this name
            # is something else's, so it is neither followed nor deleted: it is reported, because
            # silently skipping it would leave a half-published group unreconciled.
            raise ValueError('Publication transaction may not be a symlink: ' + str(item))
        if item.is_dir():
            found.append(item)
    if len(found) > MAX_PENDING:
        raise ValueError('Too many interrupted publications; reconcile '
                         + str(folder) + ' manually')
    return found


def _unstarted(folder):
    """Whether this folder is a transaction that provably never wrote a destination.

    `_stage` builds the whole folder and only then renames the journal into place, and the first
    destination replace happens later still. Once `journal.json` exists the atomic replace keeps
    it there until the folder is released, so a folder holding only this protocol's recognised
    staging entries and no journal was interrupted before it could touch the project at all.
    Recognising that case keeps a crash in a narrow window from blocking a project forever,
    while any unrecognised entry still stops recovery for an operator.
    """
    found = sorted(item.name for item in folder.iterdir())
    if 'journal.json' in found:
        return False
    if any(name not in (BACKUP, PAYLOAD) and name != '.journal.json' + TEMPORARY for name in found):
        raise ValueError('Unrecognised content in publication transaction ' + str(folder)
                         + '; reconcile it manually')
    return True


def _staged_ownership(folder):
    """The staged file names this transaction's own record says it created, else ``None``.

    Every staged copy is named by the index of the destination it belongs to, so the folder's
    journal is what proves ownership rather than the presence of a regular file. A folder whose
    journal survived gives the exact names its records name. A folder that never got one was
    interrupted before it could record itself, so ownership can only be claimed by the
    recognised per-index shape, which still names nothing this protocol did not stage.
    """
    journal = folder / 'journal.json'
    try:
        transaction = _record_value(journal, 'Publication journal')
    except (OSError, ValueError):
        return None
    if not isinstance(transaction, dict) or not isinstance(transaction.get('entries'), list):
        return None
    return {_staged_name(entry['index']) for entry in transaction['entries']
            if isinstance(entry, dict) and _valid_index(entry.get('index'))}


def _staged_owned(owned, name):
    """Whether one file name inside a publication stage is this transaction's own staging."""
    if owned is not None:
        return name in owned
    found = STAGED_NAME.fullmatch(name)
    return found is not None and _valid_index(int(found.group(1)))


def _discard(folder):
    """Release one transaction folder, deleting only the entries this protocol staged in it.

    Ownership is proved by name: the staged copies are the per-index `backup/<index>.bin` and
    `payload/<index>.bin` files the folder's own record names, so an unknown nested file such as
    an operator's own notes inside a stage is never removed on this transaction's behalf. Every
    entry is checked before the first is deleted, so a folder that holds anything unrecognised
    keeps its journal, its staged bytes and the foreign file, and is reported for manual
    reconciliation instead of being emptied or cleaned around. `rmdir` on each level only
    succeeds once it is empty, so nothing is deleted recursively and no residue is hidden.
    """
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Publication transaction path is not a directory: ' + str(folder))
    found = sorted(item.name for item in folder.iterdir())
    if any(name not in STAGED and name != '.journal.json' + TEMPORARY for name in found):
        raise ValueError('Unrecognised content in publication transaction ' + str(folder)
                         + '; reconcile it manually')
    journal = folder / 'journal.json'
    if journal.is_symlink() or (journal.exists() and not journal.is_file()):
        raise ValueError('Publication journal is not a regular file: ' + str(journal))
    owned = _staged_ownership(folder)
    staged = []
    for name in (BACKUP, PAYLOAD):
        if name not in found:
            continue
        stage = folder / name
        if stage.is_symlink() or not stage.is_dir():
            raise ValueError('Publication stage is not a directory: ' + str(stage))
        for item in sorted(stage.iterdir()):
            if not _staged_owned(owned, item.name):
                raise ValueError('Unrecognised content in publication stage: ' + str(item)
                                 + '; it was left in place and '
                                 + str(folder) + ' was kept for manual reconciliation')
            if item.is_symlink() or not item.is_file():
                raise ValueError('Unexpected entry in publication stage: ' + str(item))
            staged.append(item)
    for item in staged:
        item.unlink()
    for name in (BACKUP, PAYLOAD):
        if name in found:
            (folder / name).rmdir()
    journal.unlink(missing_ok=True)
    (folder / ('.journal.json' + TEMPORARY)).unlink(missing_ok=True)
    folder.rmdir()
    _sync(folder.parent)


def _transaction_id():
    """A sortable identifier, so pruning receipts keeps the most recent groups."""
    return '%013d-%s' % (int(time.time() * 1000), uuid.uuid4().hex[:8])


def _backup_problem(folder, entry):
    """Why this staged backup cannot be proven to hold the recorded original, else ``None``.

    A rollback that trusts a backup it has not read restores whatever happens to be in that file,
    so an interrupted group whose staged backup was truncated, padded, replaced or removed
    between the crash and the recovery would be undone into content nobody ever published. The
    backup is therefore proved here, before any destination is written: it must be a regular
    file with a single link inside this transaction's own folder, within the backup budget, and
    its bytes must hash to the original the journal recorded.
    """
    import workflow as w
    stage = folder / BACKUP
    if stage.is_symlink() or not stage.is_dir():
        return 'the staged backup directory is missing or not a real directory'
    item = stage / _staged_name(entry['index'])
    if item.is_symlink() or not item.is_file():
        return 'the staged backup for this destination is missing'
    info = item.stat()
    if info.st_nlink != 1:
        return 'the staged backup for this destination has hardlinks'
    if info.st_size > MAX_BACKUP_BYTES:
        return 'the staged backup for this destination exceeds the backup budget'
    recorded = entry.get(ORIGINAL_BYTES)
    if isinstance(recorded, int) and not isinstance(recorded, bool):
        if info.st_size != recorded:
            return 'the staged backup size no longer matches the recorded original size'
    elif recorded is not None:
        return 'malformed recorded original size'
    try:
        data = item.read_bytes()
    except OSError as exc:
        return 'the staged backup for this destination is unreadable'
    if w.digest(data) != entry['original_sha256']:
        return 'the staged backup no longer matches the recorded original content'
    return None


def _record_problem(root, entry):
    """Why this destination record is not usable data, or ``None`` when it is.

    Everything a record will later act through is checked while it is still only data: the
    declared path must be an ordinary project artifact rather than a runtime, Git, control or
    trusted-runtime location, and each field must have the type and bound the rollback protocol
    relies on. A record that fails here is refused before a single byte is written.
    """
    import workflow as w
    if not isinstance(entry, dict) or any(key not in entry for key in ENTRY_KEYS):
        return 'malformed journal record'
    if entry['state'] not in ENTRY_STATES:
        return 'unknown destination state ' + repr(entry['state'])
    index = entry['index']
    if not _valid_index(index):
        return 'destination index is out of range'
    if not isinstance(entry['path'], str) or not entry['path']:
        return 'malformed journal record'
    if not isinstance(entry['existed'], bool):
        return 'malformed journal record'
    if not isinstance(entry['bytes'], int) or isinstance(entry['bytes'], bool) \
            or not 0 <= entry['bytes'] <= MAX_OUTPUT_BYTES:
        return 'destination byte count is out of range'
    try:
        target = w.declared_path(root, entry['path'])
    except ValueError as exc:
        return str(exc)
    if w.inside(target, trusted_roots()):
        return 'it names a trusted Crewloom runtime location'
    if entry['state'] == 'pending':
        # This attempt never touched the destination, so it owns nothing there: there is nothing
        # to restore, and demanding a backup for it would invent a requirement the writer never
        # had. Its own fields still had to be well formed to get this far.
        return None
    if not isinstance(entry['new_sha256'], str) or not JOURNAL_FINGERPRINT.fullmatch(entry['new_sha256']):
        return 'destination digest is not a recorded fingerprint'
    if not entry['existed']:
        if entry['original_sha256'] is not None:
            return 'a created destination cannot record original content'
        return None
    if not isinstance(entry['mode'], int) or isinstance(entry['mode'], bool) \
            or not 0 <= entry['mode'] <= 0o7777:
        return 'missing original file mode'
    if not isinstance(entry['original_sha256'], str) \
            or not JOURNAL_FINGERPRINT.fullmatch(entry['original_sha256']):
        return 'a replaced destination must record its original fingerprint'
    return None


def _needs_backup(entry):
    """Whether undoing this destination means writing back the bytes it replaced."""
    return entry['state'] != 'pending' and entry['existed']


def _journal_problem(root, transaction, folder):
    """Why this journal is not a usable record of an unfinished group, else ``None``.

    The whole record is checked before any entry of it is acted on, and every list it carries is
    bounded, so a corrupt or hostile journal cannot make recovery walk an unbounded number of
    paths or trust a record whose own identity disagrees with the folder it was found in.
    """
    if not isinstance(transaction, dict) or any(key not in transaction for key in JOURNAL_KEYS):
        return 'malformed publication journal'
    if transaction['schema_version'] != JOURNAL_VERSION:
        return 'unknown publication journal schema version'
    if transaction['transaction'] != folder.name:
        return 'journal identity does not match the transaction folder that holds it'
    if transaction['state'] not in JOURNAL_STATES:
        return 'unknown publication journal state ' + repr(transaction['state'])
    inputs = transaction['inputs']
    if not isinstance(inputs, dict) or len(inputs) > MAX_ARTIFACTS:
        return 'malformed recorded input fingerprints'
    if any(not isinstance(key, str) or not isinstance(value, str)
           or not JOURNAL_FINGERPRINT.fullmatch(value) for key, value in inputs.items()):
        return 'malformed recorded input fingerprints'
    parents = transaction['created_parents']
    if not isinstance(parents, list) or len(parents) > MAX_PARENTS:
        return 'malformed created-parent record'
    import workflow as w
    for parent in parents:
        if not isinstance(parent, str):
            return 'malformed created-parent record'
        try:
            w.declared_path(root, parent)
        except ValueError as exc:
            return 'a created-parent record is not an ordinary project path: ' + str(exc)
    entries = transaction['entries']
    if not isinstance(entries, list) or len(entries) > MAX_ARTIFACTS:
        return 'Publication journal has no usable destination records: ' + str(folder)
    # Every record is proved usable first, so a refusal about the shape of the journal is never
    # masked by a refusal about the staged bytes of one record inside it.
    for entry in entries:
        problem = _record_problem(root, entry)
        if problem is not None:
            return problem
    # One staged backup is named by index and one destination by path, so two records may not
    # claim either: a shared index would restore the same original twice, and two spellings of
    # one destination would let one record undo the other's write. Paths are compared after they
    # resolve, because `first.txt` and `./first.txt` are the same file, and again after they are
    # folded, because `Result.txt` and `result.txt` are the same file on a case-insensitive
    # filesystem and would otherwise each pass an undo the other had already performed.
    if len({entry['index'] for entry in entries}) != len(entries):
        return 'two destination records share one staged backup index'
    if len({w.declared_path(root, entry['path']) for entry in entries}) != len(entries):
        return 'two destination records name the same path'
    if len({w.path_key(entry['path']) for entry in entries}) != len(entries):
        return 'two destination records name one path in two spellings'
    spent = 0
    for entry in entries:
        if not _needs_backup(entry):
            continue
        problem = _backup_problem(folder, entry)
        if problem is not None:
            return problem
        spent += (folder / BACKUP / _staged_name(entry['index'])).stat().st_size
        if spent > MAX_BACKUP_BYTES:
            # The same aggregate bound the writer was held to: a group may not roll back into a
            # larger set of originals than it was ever allowed to stage, however small each one
            # is on its own, and it is refused before any of them is read back.
            return 'the staged backups for this group exceed the backup budget'
    return None


def _entry_problem(root, entry):
    """Why this destination cannot be undone, or ``None`` when it can be undone safely.

    The record itself has already been proved usable by `_journal_problem`, so only the current
    bytes on disk are in question here: a destination this attempt may have written is undoable
    only while it still holds what this attempt wrote or the original it replaced.
    """
    import workflow as w
    if entry['state'] == 'pending':
        return None  # This attempt never touched the destination, so it owns nothing there.
    target = w.declared_path(root, entry['path'])
    current = _fingerprint(target)
    if current == entry['new_sha256'] or current == entry['original_sha256']:
        return None
    return ('the file no longer matches what this transaction wrote or replaced')


def _validated(root, transaction, folder):
    """Prove the whole journal usable and every original readable before a rollback byte is written.

    A rollback that discovers an ambiguous destination half way through has already undone the
    files it processed, which would leave the group in a third state that nobody recorded. The
    same holds for a staged backup that no longer holds what the journal recorded: reading it
    would restore content nobody published, and discovering that late would leave the group
    partly undone with no record of the original either. The record, every destination it names
    and every backup it needs are therefore all proved first: either the whole journal can be
    undone exactly, or none of it is touched and the journal stays for an operator.

    The destinations are re-validated through the same broker check a publication is held to,
    rather than only being fingerprinted. A digest match says the bytes are the ones this
    attempt wrote; it says nothing about what the name now is. A destination that became a hard
    link, a directory, a symlinked path or a control or trusted location after the crash holds
    matching bytes while being something this transaction no longer owns exclusively, and
    replacing it would silently break a link or destroy a name that appeared in the meantime.
    That is a refusal, decided before the first restore, with the journal kept.
    """
    problem = _journal_problem(root, transaction, folder)
    if problem is not None:
        raise ValueError('Unusable interrupted publication at ' + str(folder) + ': ' + problem
                         + '. Nothing was changed; reconcile '
                         + str(_internal(root, 'pending', folder.name)) + ' manually.')
    try:
        destinations(root, [entry['path'] for entry in transaction['entries']])
    except ValueError as exc:
        raise ValueError('Ambiguous interrupted publication at ' + str(folder) + ': ' + str(exc)
                         + '. Every destination was left untouched; reconcile '
                         + str(_internal(root, 'pending', folder.name)) + ' manually.') from exc
    for entry in transaction['entries']:
        problem = _entry_problem(root, entry)
        if problem is None:
            continue
        label = entry['path'] if isinstance(entry, dict) else '?'
        raise ValueError('Ambiguous interrupted publication at ' + str(label) + ': ' + problem
                         + '. It was left untouched; reconcile '
                         + str(_internal(root, 'pending', folder.name)) + ' manually.')


def _restore(root, entry, folder):
    """Undo one destination this attempt may have written.

    Only a destination whose current bytes still match what this attempt wrote is restored.
    `_validated` has already proved the whole journal, so reaching a foreign change here is not
    possible; anything else is left exactly as it is.
    """
    import workflow as w
    if entry['state'] == 'pending':
        return None
    target = w.declared_path(root, entry['path'])
    if _fingerprint(target) != entry['new_sha256']:
        return None
    if entry['existed']:
        data = (folder / BACKUP / _staged_name(entry['index'])).read_bytes()
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            restore = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(restore, entry['mode'])
        os.replace(restore, target)
        _sync(target.parent)
    else:
        # A file this attempt created is removed; one it found is put back byte for byte.
        target.unlink(missing_ok=True)
    return entry['path']


def _rollback(root, transaction, folder):
    """Reverse a prepared or partly applied group, newest destination first."""
    _validated(root, transaction, folder)
    restored = []
    for entry in reversed(transaction['entries']):
        restored = [item for item in [_restore(root, entry, folder)] if item] + restored
    return restored


def _recover(root):
    """Reconcile every interrupted publication; the caller already holds the project lock.

    Each prepared journal is rolled back to the content and mode it recorded, so a writer that
    was killed mid-group is undone before its residue can be mistaken for a published file. The
    whole journal is validated first, so an ambiguous destination, an unusable record or a staged
    backup that no longer holds the recorded original stops recovery having written nothing at
    all, and keeps its journal and files for an operator rather than restoring unproven bytes.

    A journal is inspected before it is read and bounded before it is parsed, so recovery stays
    usable on the one input nobody controls: the file the interrupted writer left behind.
    """
    recovered = []
    for folder in _pending(root):
        journal = folder / 'journal.json'
        if journal.is_symlink() or not journal.is_file():
            # Either this transaction was interrupted before it could write anything, or its
            # journal is not a regular file. The first is provably safe to release; the second
            # is not provable, so it stops recovery instead of being assumed.
            if journal.is_symlink() or not _unstarted(folder):
                raise ValueError('Interrupted publication has no readable journal: ' + str(folder))
            _discard(folder)
            continue
        try:
            transaction = _record_value(journal, 'Publication journal')
        except (OSError, ValueError) as exc:
            raise ValueError('Unreadable publication journal: ' + str(folder) + ' (' + str(exc) + ')') from exc
        if not isinstance(transaction, dict) or transaction.get('project_root') != str(root):
            raise ValueError('Publication journal belongs to another project: ' + str(folder))
        if transaction.get('state') in (COMMITTED, ROLLED_BACK):
            # This group is already finished and already recorded; only its staged bytes and
            # journal remain, so the destinations are not touched a second time.
            _discard(folder)
            continue
        restored = _rollback(root, transaction, folder)
        _discard(folder)
        recovered.append({'transaction': folder.name, 'restored': restored})
    return recovered


def recover(root):
    """Reconcile interrupted publications under the root lock, before managed work starts.

    Identity and ownership are the caller's to prove first: recovery rewrites project files, so
    it belongs after the preflight that establishes which project and task this is, and before
    any frozen context is built, any gate is evaluated or any acceptance is recorded.
    """
    import workflow as w
    root = Path(root).resolve()
    with w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True):
        return _recover(root)


def _private_folder(path, parents=False):
    """Create one staging directory that only its owner can read, list or enter.

    A staged backup is a full copy of whatever a destination held, which is project content the
    broker was asked to publish and not to expose. The default create mode is masked by the
    caller's umask and is world readable on a normal one, so the mode is set explicitly here
    rather than left to the environment. A directory that already exists is not widened.
    """
    path.mkdir(parents=parents, exist_ok=True)
    os.chmod(path, 0o700)


def _write_staged(path, data):
    """Write one staged copy of project content that only its owner can read."""
    path.write_bytes(data)
    os.chmod(path, 0o600)


def _stage(root, targets, artifacts, expected_inputs):
    """Validate and journal the whole group, with a backup and a staged payload per output."""
    import workflow as w
    ident = _transaction_id()
    folder = _internal(root, 'pending', ident)
    if folder.exists():
        raise ValueError('Transaction identifier collision; retry the publication')
    _private_folder(folder, parents=True)
    _private_folder(folder / BACKUP)
    _private_folder(folder / PAYLOAD)
    entries = []
    created = []
    spent = 0
    for index, relative in enumerate(targets):
        target = targets[relative]
        existed = target.is_file()
        entry = {'index': index, 'path': relative, 'state': 'pending', 'existed': existed,
                 'mode': None, 'bytes': len(artifacts[relative]), ORIGINAL_BYTES: 0,
                 'original_sha256': None, 'new_sha256': w.digest(artifacts[relative])}
        if existed:
            original = target.read_bytes()
            spent += len(original)
            if spent > MAX_BACKUP_BYTES:
                raise ValueError('Output backup budget exceeded; publish a smaller group')
            entry['mode'] = target.stat().st_mode & 0o7777
            # The original size is recorded beside its digest so a later recovery can refuse a
            # truncated or padded backup before hashing it, and so a journal written by this
            # protocol always carries enough to prove its staged bytes exactly.
            entry[ORIGINAL_BYTES] = len(original)
            entry['original_sha256'] = w.digest(original)
            _write_staged(folder / BACKUP / _staged_name(index), original)
        _write_staged(folder / PAYLOAD / _staged_name(index), artifacts[relative])
        # A destination directory this attempt will have to create is recorded so an
        # interrupted publication can leave the tree the way it found it.
        missing = []
        walk = target.parent
        while walk != root and not walk.exists():
            missing.append(str(walk.relative_to(root)))
            walk = walk.parent
        created = missing + created
        entries.append(entry)
    transaction = {'schema_version': JOURNAL_VERSION, 'transaction': ident, 'project_root': str(root),
                   'created_at': _timestamp(), 'state': 'prepared', 'inputs': dict(expected_inputs),
                   'created_parents': created, 'entries': entries}
    _write_record(folder / 'journal.json', transaction)
    return transaction, folder


def _apply(root, transaction, folder):
    """Write each staged output, journalling the intent before every destination replace.

    The intent is recorded before the rename rather than after it, so a process killed inside
    the rename still leaves a journal that knows this destination may hold bytes it wrote.
    """
    import workflow as w
    journal = folder / 'journal.json'
    for entry in transaction['entries']:
        target = w.declared_path(root, entry['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        entry['state'] = 'replacing'
        _write_record(journal, transaction)
        data = (folder / PAYLOAD / _staged_name(entry['index'])).read_bytes()
        # The staged bytes are written beside the destination and renamed in, so the rename is
        # atomic within one filesystem and a reader never sees a half-written output. A writer
        # killed here leaves that temporary file behind; it is not this protocol's to guess at,
        # so it is left for the operator rather than deleted by a predictable name.
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            staged = Path(stream.name)
            staged.write_bytes(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, entry['mode'] if entry['existed'] else 0o644)
        os.replace(staged, target)
        entry['state'] = 'replaced'
        _write_record(journal, transaction)
        _sync(target.parent)


def _receipt(root, transaction, state, moment, extra):
    """Write one bounded, durable record of a group, before its journal is released."""
    receipts = _internal(root, 'receipts')
    receipts.mkdir(parents=True, exist_ok=True)
    receipt = {'schema_version': JOURNAL_VERSION, 'transaction': transaction['transaction'],
               'project_root': transaction['project_root'], 'state': state, moment: _timestamp(),
               'inputs': transaction['inputs'], **extra}
    _write_record(receipts / (transaction['transaction'] + '.json'), receipt)
    return receipt


def _prune(receipts):
    """Bound receipt storage by dropping the oldest records, never the newest."""
    kept = [item for item in receipts.iterdir()
            if not item.is_symlink() and item.is_file()
            and item.name.endswith(RECEIPT_SUFFIXES)]
    for stale in sorted(kept)[:-MAX_RECEIPTS]:
        stale.unlink()


def _abandon(root, transaction, folder, restored):
    """Record a reverted group and release its journal, so the failure is history not residue."""
    _receipt(root, transaction, ROLLED_BACK, 'rolled_back_at',
             {'outputs': {entry['path']: entry['new_sha256'] for entry in transaction['entries']},
              'restored': restored})
    transaction['state'] = ROLLED_BACK
    _write_record(folder / 'journal.json', transaction)
    _discard(folder)
    _prune(_internal(root, 'receipts'))


def _commit(root, transaction, folder):
    """Record the committed group durably, then release the journal and its staged bytes.

    The receipt exists before the journal is released, so a step that completed can always name
    the transaction that published its outputs and the hashes it published.
    """
    receipt = _receipt(root, transaction, COMMITTED, 'committed_at',
                       {'outputs': {entry['path']: entry['new_sha256'] for entry in transaction['entries']}})
    transaction['state'] = COMMITTED
    _write_record(folder / 'journal.json', transaction)
    _discard(folder)
    _prune(_internal(root, 'receipts'))
    return receipt


def publish(root, artifacts, expected_inputs):
    """Publish one declared output group as a single recoverable transaction.

    Every input fingerprint, destination and payload is checked before the first destination is
    written, so a group that cannot succeed writes nothing at all. The group is then staged and
    journalled under `.crewloom`, applied one file at a time under the project lock, and rolled
    back to the recorded original content and mode if any write fails.

    A filesystem cannot make several files appear at once, so this is deliberately not claimed to
    be an instant multi-file atomic change: a reader that ignores the project lock can observe
    the group half applied. What is guaranteed is narrower and real. Every managed writer
    serialises on the same lock, and an interrupted group is reconciled by the next managed
    publication before it writes anything, so the project converges instead of accumulating a
    half-published group.

    The receipt is written before this returns, so a step is only ever recorded complete, or its
    executor evidence promoted to a lesson, against a group that is already durable on disk.
    """
    import workflow as w
    root = Path(root).resolve()
    with w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True):
        _recover(root)
        if w.hashes(root, list(expected_inputs)) != expected_inputs:
            raise ValueError('Inputs changed during execution; artifacts rejected')
        targets = destinations(root, list(artifacts))
        if any(not isinstance(data, bytes) or not data for data in artifacts.values()):
            raise ValueError('Outputs must be nonempty regular files')
        if sum(len(data) for data in artifacts.values()) > MAX_OUTPUT_BYTES:
            raise ValueError('Output artifact budget exceeded')
        transaction, folder = _stage(root, targets, artifacts, expected_inputs)
        try:
            _apply(root, transaction, folder)
        except BaseException as failure:
            # The caller's own error is what they need to see, so a rollback that succeeds
            # leaves it untouched. A rollback that cannot finish is a different and louder
            # problem: it is raised with the original failure as its cause, so the refused
            # reconciliation and the write that caused it are both in the traceback rather than
            # one silently replacing the other.
            try:
                restored = _rollback(root, transaction, folder)
            except (ValueError, OSError) as refusal:
                raise refusal from failure
            # A fully reverted group is finished. Its receipt keeps the failed attempt as
            # bounded history, and its journal is released so the next publication does not
            # reconcile it a second time.
            _abandon(root, transaction, folder, restored)
            raise
        return _commit(root, transaction, folder)


def execute(root, step, image_id, timeout):
    import workflow as w
    outputs=destinations(root,step['outputs'])
    if len(step['inputs'])>MAX_ARTIFACTS:raise ValueError('Too many input artifacts')
    # Inputs are staged into a shadow tree under the names the step declared, so two spellings
    # of one input would silently drop one of them there. The folded rule is the same one the
    # output group is held to.
    if len({w.path_key(item) for item in step['inputs']})!=len(step['inputs']):
        raise ValueError('Input artifact names collide on a case-insensitive or normalizing filesystem')
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
