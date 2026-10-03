# -*- coding: utf-8 -*-
"""Stub for Sublime Text's built-in ``sublime`` module.

Sublime plugins run inside the editor's embedded Python, where ``sublime`` is a
built-in module provided by the plugin host. Outside of Sublime (e.g. when
running this suite in a normal Python/venv) that module does not exist, so we
register a minimal stub here to let the tests execute.

This file is only used by the test runner and is never loaded by the plugin
itself.
"""

import sys
import types
import os
import tempfile

# Redirect the plugin's log to a temp file so running the suite doesn't
# overwrite the real Sublime log at ~/.sync_settings_reborn/sync.log. The
# logger honours this env var at import time.
os.environ['SYNC_SETTINGS_REBORN_LOG_FILE'] = os.path.join(
    tempfile.gettempdir(), 'sync_settings_reborn_test.log'
)


sublime = types.ModuleType('sublime')

# Dialog result constants returned by yes_no_cancel_dialog
sublime.DIALOG_YES = 1
sublime.DIALOG_NO = 2
sublime.DIALOG_CANCEL = 3


class Settings:
    def __init__(self, data=None):
        self._data = dict(data or {})

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def erase(self, key):
        self._data.pop(key, None)


def load_settings(name):
    return Settings()


def save_settings(name):
    pass


def yes_no_cancel_dialog(*args, **kwargs):
    return sublime.DIALOG_YES


# No-op stubs for the APIs the plugin calls but tests do not need to exercise.
sublime.status_message = lambda *a, **k: None
sublime.message_dialog = lambda *a, **k: None
sublime.set_clipboard = lambda *a, **k: None
sublime.active_window = lambda *a, **k: None
# Run main-thread callbacks inline: production code schedules these with
# set_timeout from worker threads; in tests there is no event loop, so execute
# synchronously to preserve the same main-thread semantics.
sublime.set_timeout = lambda fn, *a, **k: fn()
sublime.version = lambda: '4143'
sublime.packages_path = lambda: '/tmp'
sublime.installed_packages_path = lambda: '/tmp/Installed Packages'
sublime.list_packages = lambda: []

sublime.load_settings = load_settings
sublime.save_settings = save_settings
sublime.yes_no_cancel_dialog = yes_no_cancel_dialog

sys.modules['sublime'] = sublime


# sublime_plugin is another Sublime built-in (provides WindowCommand, TextCommand,
# etc.). Command modules import it at module level, so stub it for the suite.
sublime_plugin = types.ModuleType('sublime_plugin')


class WindowCommand:
    pass


class TextCommand:
    pass


sublime_plugin.WindowCommand = WindowCommand
sublime_plugin.TextCommand = TextCommand
sys.modules['sublime_plugin'] = sublime_plugin
