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


def migrate_legacy():
    new = sublime.load_settings(filename)
    legacy = sublime.load_settings(LEGACY_FILENAME)
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
    sublime.load_settings(filename).set(key, value)
    save()


def get(key):
    return sublime.load_settings(filename).get(key)
