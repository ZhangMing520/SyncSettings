# -*- coding: utf-8 -*-

import os

import sublime_plugin

from . import decorators
from .. import backup as backup_lib
from ..libs import settings
from ..thread_progress import ThreadProgress


class SyncSettingsRebornBackupCommand(sublime_plugin.WindowCommand):
    def run(self, packages_only=False):
        self.packages_only = packages_only
        default = backup_lib.default_backup_path()
        if settings.get('prompt_for_location'):
            self.window.show_input_panel(
                'Backup zip path:', default, self._do_backup, None, None
            )
        else:
            self._do_backup(default)

    def _do_backup(self, target):
        target = (target or '').strip()
        if not target:
            return
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._failed = False
        ThreadProgress(
            target=lambda: self._backup(target),
            message='backing up',
            success_message='backup created',
            success_when=lambda: not self._failed,
        )

    def _backup(self, target):
        try:
            backup_lib.create_backup_zip(target, packages_only=self.packages_only)
        except Exception as e:
            decorators.report_error(self, e)


class SyncSettingsRebornBackupPackageListCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command('sync_settings_reborn_backup', {'packages_only': True})
