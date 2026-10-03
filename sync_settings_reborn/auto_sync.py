# -*- coding: utf-8 -*-

"""Background auto-sync driven by the `auto_upgrade` option.

When `auto_upgrade` is true and the user has configured an `access_token`
(and, for pulls, a `gist_id`), this module keeps the local `Packages/User`
mirror in sync with the backing gist, mimicking VS Code's Settings Sync:

  * on startup it pulls the latest gist (the original auto_upgrade behaviour);
  * on a background timer (default every few minutes) it both pulls remote
    changes and pushes local changes, so edits made on any machine propagate
    without a manual upload/download.

The loop is a three-way merge against the per-file content snapshot we last
synced. That snapshot is persisted in ``sync.json`` (alongside the gist
revision), so an edit made while Sublime was closed is still recognised as a
local change after restart: it is pushed, and if the same file also changed
remotely it is detected as a conflict — logged, backed up, and resolved in
favour of the remote (the gist stays the shared source of truth) instead of
one side being silently lost. File deletions propagate both ways. Everything
runs on a daemon thread, so it never blocks Sublime.
"""

import hashlib
import os
import threading
import time

import sublime

from .libs import settings, path
from .libs.gist import Gist, NotFoundError
from .libs.logger import logger
from . import sync_version as version, sync_manager as manager


DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
MIN_INTERVAL_MINUTES = 1

# State persisted per sync (sync.json keys):
#   hash       — gist revision (cheap "did the remote move?" pre-check)
#   created_at — revision timestamp
#   files      — {encoded name: sha256} common ancestor for the three-way merge


def should_auto_sync():
    """True when auto-sync is allowed to run at all.

    Requires the option on plus an access token. Pulls also need a gist id,
    but pushing can create one, so the token is the only hard requirement.
    """
    if not settings.get('auto_upgrade'):
        return False
    if not settings.get('access_token'):
        logger.info('auto_upgrade is on but no access_token is configured; '
                    'auto-sync disabled')
        return False
    return True


def _sha(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _on_main(fn, timeout=None):
    """Run fn on Sublime's main thread.

    Dialogs/status must run there, and ``sublime.list_packages()`` only works
    there. With ``timeout`` the worker waits up to that many seconds and gets
    fn's return value; without it the call is fire-and-forget. When nothing
    pumps the event loop (headless tests) fn runs inline.
    """
    box = {}
    done = threading.Event()

    def run():
        # The inline fallback can race the callback already queued on the main
        # loop; run the payload at most once.
        if box.get('ran'):
            return
        box['ran'] = True
        try:
            box['value'] = fn()
        except Exception as e:
            logger.debug('main-thread callback failed: {}'.format(e))
        done.set()

    try:
        sublime.set_timeout(run, 0)
    except Exception:
        run()
        return box.get('value')
    if timeout is not None and not done.wait(timeout):
        run()
    return box.get('value')


def _snapshot_installed():
    """Take the installed-package snapshot on the MAIN thread.

    ``sublime.list_packages()`` only works there (it raises from a worker
    thread). A failed snapshot returns None, which the collector treats as
    "do not filter" (fail-open).
    """
    return _on_main(manager.installed_packages_snapshot, timeout=0.2)


def _current_files(installed='unset'):
    if installed == 'unset':
        installed = _snapshot_installed()
    return manager.get_files(installed=installed)


def _content_hashes(files):
    return {k: _sha(v['content']) for k, v in files.items()}


def _current_hashes():
    """Per-file content hashes of what we would upload right now.

    Uses the same collection path as the real upload (filters, uninstalled
    skip, token exclusion), so a change only to a token / empty / excluded
    file never triggers a push.
    """
    return _content_hashes(_current_files())


def _load_state():
    """Return ``(gist_revision, {name: hash})`` from sync.json."""
    info = version.get_local_version() or {}
    files = info.get('files')
    return info.get('hash'), dict(files) if isinstance(files, dict) else {}


def _head_commit(g):
    """The gist's current commit as ``(version, committed_at)``."""
    commit = (g.get('history') or [{}])[0] if isinstance(g, dict) else {}
    return commit.get('version'), commit.get('committed_at')


def _normalise_gist_files(g):
    """Map GitHub's gist payload to ``{encoded_name: content}``.

    A value of None means the file exists remotely but its content is not
    present in the listing (GitHub truncates large files); callers then skip
    it rather than treating it as a deletion.
    """
    files = {}
    for name, meta in (g.get('files') or {}).items():
        if not isinstance(meta, dict):
            continue
        content = meta.get('content')
        files[name] = content if content and not meta.get('truncated') else None
    return files


def _build_payload(keys, current, hashes, baseline):
    """Build a gist PATCH payload and the matching new baseline for ``keys``.

    A present file uploads its content (``{name: {'content': ...}}``); a key
    missing from disk is deleted remotely (``{name: None}``) only when the
    file is genuinely gone, not when it was merely filtered out.
    """
    payload, new_baseline = {}, dict(baseline)
    for k in keys:
        if k in current:
            payload[k] = {'content': current[k]['content']}
            new_baseline[k] = hashes[k]
        elif not manager.user_file_exists(k):
            payload[k] = None
            new_baseline.pop(k, None)
    return payload, new_baseline


def _fetch_remote():
    """Fetch the gist once and return
    ``(revision_id, committed_at, {encoded_name: content})``.

    Returns ``(None, None, {})`` on a transient failure (retry next cycle);
    raises NotFoundError on a deleted gist so the caller can surface it once.
    Fetching the full gist every cycle doubles as the "did the remote move?"
    pre-check — settings gists are small, and it avoids a second round trip
    and a second timeout window when the gist changed.
    """
    gid = settings.get('gist_id')
    if not gid:
        return None, None, {}
    try:
        g = Gist.from_settings().get(gid)
        rev, committed_at = _head_commit(g)
        return rev, committed_at, _normalise_gist_files(g)
    except NotFoundError:
        raise
    except Exception as e:
        logger.exception(e)
        return None, None, {}


def _apply_remote(remote_files, to_pull):
    """Write only the requested gist files into Packages/User (a delta pull)."""
    files = {k: remote_files[k] for k in to_pull if k in remote_files}
    if not files:
        return
    try:
        manager.write_user_files(files, preserve_packages=True)
    except Exception as e:
        logger.exception(e)


def _push(payload):
    """Upload a gist ``files`` payload: ``{name: {'content': ...}}`` to update
    a file, ``{name: None}`` to delete one (Gist PATCH semantics).

    Creates the gist when no gist_id is configured (deletion entries are not
    valid there). Returns the gist response, or None on failure.
    """
    if not payload:
        logger.info('auto-sync push skipped: no files to upload')
        return None
    gid = settings.get('gist_id')
    if not gid and any(v is None for v in payload.values()):
        logger.warning('auto-sync cannot delete files while creating the gist; '
                       'retrying next cycle')
        return None
    try:
        gist_api = Gist.from_settings()
        data = {'files': payload}
        if gid:
            g = gist_api.update(gid, data=data)
        else:
            data['description'] = 'SyncSettingsReborn backup'
            g = gist_api.create(data)
            settings.update('gist_id', g['id'])
            logger.info('auto-sync created gist {}'.format(g['id']))
        return g
    except Exception as e:
        logger.exception(e)
        return None


def _backup_conflicts(conflicts, current):
    """Save the local version of each conflicted file so nothing is lost.

    Resolving a conflict by taking the remote version overwrites (or deletes)
    the local one; stashing it under
    ``~/.sync_settings_reborn/conflicts/<timestamp>/`` lets the user recover
    their edit by hand.
    """
    if not conflicts:
        return
    stamp = path.join(os.path.dirname(version.file_path),
                      'conflicts', str(int(time.time())))
    for k in conflicts:
        content = current.get(k, {}).get('content')
        if content is None:
            continue
        dest = path.join(stamp, k)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'w') as f:
                f.write(content)
        except Exception as e:
            logger.warning('could not back up conflicted file {}: {}'.format(k, e))


class AutoSync:
    """A restartable background auto-sync loop using three-way merge."""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._interval = DEFAULT_INTERVAL_SECONDS
        # The snapshot we last synced (per-file content hashes). This is the
        # common ancestor used to compute local vs remote deltas, and it is
        # persisted to sync.json so offline edits survive a restart.
        self._last_synced = {}
        # The gist revision we last observed, for a cheap unchanged pre-check.
        self._last_seen_remote = None
        self._last_committed_at = None
        # When set to a gist id that gist 404'd: sync is actually paused (no
        # more polls of it) and the dialog was shown, until gist_id changes.
        self._missing_gist = None

    def _configure_interval(self):
        val = settings.get('auto_sync_interval')
        try:
            minutes = int(val)
        except (TypeError, ValueError):
            return
        if minutes >= MIN_INTERVAL_MINUTES:
            self._interval = minutes * 60
        else:
            logger.warning(
                'auto_sync_interval must be an integer number of minutes '
                '>= {}; keeping the default of {} minutes'.format(
                    MIN_INTERVAL_MINUTES, DEFAULT_INTERVAL_SECONDS // 60))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._configure_interval()
        self._stop.clear()
        self._missing_gist = None
        # Restore the persisted common ancestor. We deliberately do NOT seed it
        # from the current disk state: doing so would make edits performed
        # while Sublime was closed look "already synced" after a restart.
        rev, files = _load_state()
        self._last_synced = files
        self._last_seen_remote = rev
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info('auto-sync started (interval {}s)'.format(self._interval))

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        logger.info('auto-sync stopped')

    def _run(self):
        # Brief grace period so Sublime has finished loading settings before
        # the first network call.
        if self._stop.wait(min(5, self._interval)):
            return
        while not self._stop.is_set():
            try:
                self._sync_once()
            except Exception as e:
                logger.exception(e)
            if self._stop.wait(self._interval):
                break

    # ---- state bookkeeping -------------------------------------------------

    def _persist_state(self):
        version.update_config_file({
            'hash': self._last_seen_remote,
            'created_at': self._last_committed_at or '',
            'files': self._last_synced,
        })

    def adopt(self, rev, committed_at, baseline):
        """Adopt an externally established sync point (a manual Upload or
        Download command) so its files don't look like fresh deltas here."""
        self._last_seen_remote = rev
        self._last_committed_at = committed_at
        self._last_synced = dict(baseline)
        self._missing_gist = None
        try:
            self._persist_state()
        except Exception as e:
            logger.warning('auto-sync could not persist adopted state: {}'.format(e))

    def _record_push(self, g):
        self._last_seen_remote, self._last_committed_at = _head_commit(g)
        self._missing_gist = None
        logger.info('auto-sync push complete')

    def _warn_missing_gist(self, gid):
        # Caller only reaches here when the gist 404s; the id guard makes the
        # dialog one-shot and keeps the pause honest across settings changes.
        if self._missing_gist == gid:
            return
        self._missing_gist = gid
        logger.error('auto-sync gist `{}` is gone (404); pausing until the '
                     'gist_id setting changes'.format(gid))
        msg = (
            'SyncSettingsReborn:\n\n'
            'The configured gist no longer exists (or the token cannot access it).\n\n'
            'Automatic sync is paused. Clear or change `gist_id` in the settings '
            'to resume.'
        )
        _on_main(lambda: sublime.message_dialog(msg))

    # ---- sync cycles -------------------------------------------------------

    def _sync_once(self):
        gid = settings.get('gist_id')
        if self._missing_gist is not None:
            if not gid or self._missing_gist == gid:
                # Still paused on the dead gist; a cleared gist_id falls
                # through to the initial push below.
                if gid:
                    return
            else:
                # gist_id points somewhere else: retry it.
                self._missing_gist = None
        if not gid:
            # No gist yet: publish the whole mirror so the first gist is
            # complete, no matter what the persisted baseline remembers.
            self._initial_push()
            return
        try:
            rev, committed_at, remote_files = _fetch_remote()
        except NotFoundError:
            self._warn_missing_gist(gid)
            return
        if rev is None and not remote_files:
            # Transient failure; retry next cycle rather than guessing.
            return
        if rev == self._last_seen_remote:
            # Remote is unchanged since we last looked: only push local edits.
            self._push_local_delta()
            return
        self._merge(rev, committed_at, remote_files)

    def _initial_push(self):
        current = _current_files()
        if not current:
            logger.info('auto-sync push skipped: no files to upload')
            return
        current_hashes = _content_hashes(current)
        # Every collected file goes into the brand-new gist; an empty baseline
        # means there are no deletions to consider.
        payload, new_baseline = _build_payload(set(current), current,
                                               current_hashes, {})
        g = _push(payload)
        if g is None:
            return
        self._record_push(g)
        self._last_synced = new_baseline
        self._persist_state()

    def _push_local_delta(self):
        """Push only the files that changed (or were deleted) locally, no
        remote merge."""
        current = _current_files()
        current_hashes = _content_hashes(current)
        last = self._last_synced or {}
        changed = {k for k in set(current_hashes) | set(last)
                   if current_hashes.get(k) != last.get(k)}
        payload, new_baseline = _build_payload(changed, current,
                                               current_hashes, last)
        if not payload:
            return
        g = _push(payload)
        if g is None:
            # Keep the baseline untouched; the whole delta is retried.
            return
        # The PATCH moved the gist: record its revision so the next cycle
        # doesn't fetch-and-merge a revision we already know.
        self._record_push(g)
        self._last_synced = new_baseline
        self._persist_state()

    def _merge(self, rev, committed_at, remote_files):
        installed = _snapshot_installed()
        current = _current_files(installed)
        current_hashes = _content_hashes(current)
        # A present key with falsy content means the gist content is
        # unavailable (truncated); such keys must not be treated as deletions.
        remote_hashes = {k: _sha(v) for k, v in remote_files.items() if v}
        last = dict(self._last_synced or {})

        all_keys = set(current_hashes) | set(last) | set(remote_hashes)
        local_changed = {k for k in all_keys if current_hashes.get(k) != last.get(k)}
        remote_changed = {k for k in all_keys if remote_hashes.get(k) != last.get(k)}

        # A conflict: the same file moved both locally and remotely. The gist
        # wins; back up recoverable local edits first (covers both
        # remote-modified and remote-deleted cases).
        conflicts = sorted(local_changed & remote_changed)
        backup_keys = [k for k in conflicts if k in current]
        if backup_keys:
            names = ', '.join(path.decode(k) for k in backup_keys)
            msg = 'SyncSettingsReborn: auto-sync conflict on: {}'.format(names)
            logger.warning(msg)
            _on_main(lambda m=msg: sublime.status_message(m))
            _backup_conflicts(backup_keys, current)

        # Delta pull (conflicts resolve to the remote side, including a
        # remote deletion). Classify into write / delete / unavailable.
        pull_keys = (remote_changed - local_changed) | set(conflicts)
        pull_present, pull_deleted, pull_unavailable = [], [], []
        for k in pull_keys:
            if k not in remote_files:
                pull_deleted.append(k)
            elif remote_files[k]:
                pull_present.append(k)
            else:
                pull_unavailable.append(k)
        if pull_unavailable:
            logger.warning('auto-sync skipped files whose gist content is '
                           'unavailable (too large/truncated): {}'.format(
                               ', '.join(sorted(pull_unavailable))))
        if pull_present:
            _apply_remote(remote_files, set(pull_present))
        if pull_deleted:
            manager.delete_user_files(sorted(pull_deleted))

        # Re-collect AFTER writing: write_user_files may merge content
        # (Package Control installed_packages union), and the push must carry
        # that merged result, not a stale pre-pull copy.
        if pull_present or pull_deleted:
            current = _current_files(installed)
            current_hashes = _content_hashes(current)

        # Pulled files become part of the baseline at their post-write hashes;
        # remotely deleted files leave it. Local deltas then add/update/remove
        # theirs through the same payload builder the other paths use.
        new_baseline = dict(last)
        for k in pull_present:
            if k in current_hashes:
                new_baseline[k] = current_hashes[k]
        for k in pull_deleted:
            new_baseline.pop(k, None)

        # Locally changed, non-conflict files are pushed. A pulled file whose
        # on-disk content differs from the remote hash (a local merge result)
        # is pushed too, so the union converges across machines.
        push_keys = set(local_changed) - set(conflicts)
        push_keys |= {k for k in pull_present
                      if k in current_hashes and current_hashes[k] != remote_hashes.get(k)}
        payload, new_baseline = _build_payload(
            push_keys, current, current_hashes, new_baseline)
        # Keys filtered out locally but still on disk are kept on the gist:
        # _build_payload simply leaves them out of the payload/baseline delta.

        if payload:
            g = _push(payload)
            if g is None:
                # Network/API failure: do not move the baseline; the whole
                # merge is retried next cycle (pulls are idempotent).
                return
            self._record_push(g)

        self._last_seen_remote = rev
        self._last_committed_at = committed_at
        self._last_synced = new_baseline
        self._persist_state()


# Module-level singleton so plugin_loaded / plugin_unloaded can manage it, and
# repeated reloads (the 1_reloader path) don't spawn duplicate loops.
_auto_sync = AutoSync()


def startup_sync():
    """Start the background auto-sync loop (called from the package root's
    plugin_loaded, since Sublime only invokes that hook on root modules)."""
    if not should_auto_sync():
        return
    _auto_sync.start()


def shutdown():
    _auto_sync.stop()


def _adopt_gist(g, baseline, kind):
    try:
        rev, committed_at = _head_commit(g)
        _auto_sync.adopt(rev, committed_at, baseline)
    except Exception as e:
        logger.warning('auto-sync could not adopt manual {}: {}'.format(kind, e))


def adopt_manual_upload(files, g):
    """Re-baseline auto-sync after a successful manual Upload."""
    baseline = {k: _sha(v['content']) for k, v in files.items()
                if isinstance(v, dict) and v.get('content') is not None}
    _adopt_gist(g, baseline, 'upload')


def adopt_manual_download(g):
    """Re-baseline auto-sync after a successful manual Download.

    Files whose content is truncated in the gist listing are skipped; they
    simply re-converge on the next background merge.
    """
    baseline = {k: _sha(v) for k, v in _normalise_gist_files(g).items() if v}
    _adopt_gist(g, baseline, 'download')
