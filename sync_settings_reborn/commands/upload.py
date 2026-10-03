# -*- coding: utf-8 -*-

import sublime
import sublime_plugin

from . import decorators
from .. import sync_version as version, sync_manager as manager
from ..libs import settings
from ..libs import gist
from ..thread_progress import ThreadProgress


class SyncSettingsRebornUploadCommand(sublime_plugin.WindowCommand):
    def upload(self):
        files = manager.get_files()
        if not len(files):
            sublime.status_message('SyncSettingsReborn: there are not files to upload')
            return
        try:
            g = gist.Gist(
                token=settings.get('access_token'),
                http_proxy=settings.get('http_proxy'),
                https_proxy=settings.get('https_proxy')
            ).update(
                settings.get('gist_id'),
                data={'files': files}
            )
            commit = g['history'][0]
            version.update_config_file({
                'hash': commit['version'],
                'created_at': commit['committed_at'],
            })
        except gist.NotFoundError as e:
            msg = (
                'SyncSettingsReborn:\n\n'
                '{}\n\n'
                'Please check if the access token was created with the gist scope.\n\n'
                'If the access token is correct, please, delete the value of `gist_id` property manually.'
            )
            sublime.message_dialog(msg.format(str(e)))
        except Exception as e:
            decorators.report_error(self, e)

    @decorators.check_settings('gist_id', 'access_token')
    def run(self):
        self._failed = False
        ThreadProgress(
            target=self.upload,
            message='uploading files',
            success_message='files uploaded',
            success_when=lambda: not self._failed
        )
