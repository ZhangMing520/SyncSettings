# -*- coding: utf-8 -*-

import sublime_plugin

from . import decorators
from .. import backup as backup_lib
from ..libs import settings
from ..thread_progress import ThreadProgress


class SyncSettingsRebornRestoreCommand(sublime_plugin.WindowCommand):
    def run(self):
        default = backup_lib.default_backup_path()
        if settings.get('prompt_for_location'):
            self.window.show_input_panel(
                'Restore zip path:', default, self._do_restore, None, None
            )
        else:
            self._do_restore(default)

    def _do_restore(self, source):
        source = (source or '').strip()
        if not source:
            return
        self._failed = False
        ThreadProgress(
            target=lambda: self._restore(source),
            message='restoring',
            success_message='restore done',
            success_when=lambda: not self._failed,
        )

    def _restore(self, source):
        try:
            backup_lib.restore_backup_zip(
                source, preserve_packages=backup_lib.preserve_packages()
            )
        except Exception as e:
            decorators.report_error(self, e)
