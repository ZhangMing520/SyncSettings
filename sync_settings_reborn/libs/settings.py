# -*- coding: utf-8 -*-

import sublime

filename = 'SyncSettingsReborn.sublime-settings'

# Legacy package (mfuentesg/SyncSettings) stored its config under this file.
# We copy the connection settings over so existing users don't have to
# re-enter their gist id / access token.
LEGACY_FILENAME = 'SyncSettings.sublime-settings'

_MIGRATE_KEYS = (
    'gist_id',
    'access_token',
    'http_proxy',
    'https_proxy',
    'excluded_files',
    'included_files',
)

# Loaded Settings objects are cached so the per-file exclude/include checks in
# sync_manager don't call into sublime.load_settings repeatedly. The objects are
# live (Sublime keeps them in sync with disk), so no value staleness.
_cache = {}


def _load_cached(filename):
    cached = _cache.get(filename)
    if cached is None:
        cached = sublime.load_settings(filename)
        _cache[filename] = cached
    return cached


def migrate_legacy():
    new = _load_cached(filename)
    legacy = _load_cached(LEGACY_FILENAME)
    migrated = False
    for key in _MIGRATE_KEYS:
        legacy_val = legacy.get(key)
        if legacy_val in (None, ''):
            continue
        if new.get(key) in (None, ''):
            new.set(key, legacy_val)
            migrated = True
    if migrated:
        sublime.save_settings(filename)


def save():
    sublime.save_settings(filename)


def update(key, value):
    _load_cached(filename).set(key, value)
    save()


def get(key):
    return _load_cached(filename).get(key)
