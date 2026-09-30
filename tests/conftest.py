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
sublime.set_timeout = lambda fn, *a, **k: None  # do not execute deferred work
sublime.version = lambda: '4143'
sublime.packages_path = lambda: '/tmp'

sublime.load_settings = load_settings
sublime.save_settings = save_settings
sublime.yes_no_cancel_dialog = yes_no_cancel_dialog

sys.modules['sublime'] = sublime
