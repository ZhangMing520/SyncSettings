# -*- coding: utf-8 -*-

import os

import sublime_plugin

from . import decorators
from .. import backup as backup_lib
from ..libs import settings
from ..thread_progress import ThreadProgress


class SyncSettingsRebornSyncOnlineDefineFolderCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.show_input_panel(
            'Online sync folder:', settings.get('online_sync_folder') or '',
            self._set, None, None
        )

    def _set(self, folder):
        folder = (folder or '').strip()
        if folder:
            settings.update('online_sync_folder', folder)


class SyncSettingsRebornSyncOnlinePushCommand(sublime_plugin.WindowCommand):
    @decorators.check_settings('online_sync_folder')
    def run(self):
        target = os.path.join(settings.get('online_sync_folder'), backup_lib.DEFAULT_BACKUP_NAME)
        self._failed = False
        ThreadProgress(
            target=lambda: self._push(target),
            message='syncing online (push)',
            success_message='pushed',
            success_when=lambda: not self._failed,
        )

    def _push(self, target):
        try:
            backup_lib.create_backup_zip(target)
        except Exception as e:
            decorators.report_error(self, e)


class SyncSettingsRebornSyncOnlinePullCommand(sublime_plugin.WindowCommand):
    @decorators.check_settings('online_sync_folder')
    def run(self):
        source = os.path.join(settings.get('online_sync_folder'), backup_lib.DEFAULT_BACKUP_NAME)
        self._failed = False
        ThreadProgress(
            target=lambda: self._pull(source),
            message='syncing online (pull)',
            success_message='pulled',
            success_when=lambda: not self._failed,
        )

    def _pull(self, source):
        try:
            if not os.path.exists(source):
                raise FileNotFoundError(
                    'no backup zip found in online sync folder: {}'.format(source)
                )
            backup_lib.restore_backup_zip(
                source, preserve_packages=backup_lib.preserve_packages()
            )
        except Exception as e:
            decorators.report_error(self, e)
