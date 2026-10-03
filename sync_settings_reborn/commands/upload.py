# -*- coding: utf-8 -*-

import sublime
import sublime_plugin

from . import decorators
from .. import auto_sync, sync_version as version, sync_manager as manager
from ..libs import settings
from ..libs import gist
from ..libs.logger import logger
from ..thread_progress import ThreadProgress


class SyncSettingsRebornUploadCommand(sublime_plugin.WindowCommand):
    def upload(self, installed=None):
        files = manager.get_files(installed=installed)
        if not len(files):
            logger.warning('no files collected to upload (check exclude/include settings)')
            sublime.status_message('SyncSettingsReborn: there are not files to upload')
            return
        gid = settings.get('gist_id')
        logger.info('uploading {} file(s) to gist {}'.format(len(files), gid or '(new)'))
        try:
            gist_api = gist.Gist.from_settings()
            if gid:
                # Update the existing gist.
                g = gist_api.update(gid, data={'files': files})
            else:
                # No gist yet: create one and remember it so the next upload
                # updates instead of creating again. No description prompt, no
                # "backfill gist_id?" question — this is the one-click reset path.
                g = gist_api.create({'files': files, 'description': 'SyncSettingsReborn backup'})
                settings.update('gist_id', g['id'])
                logger.info('created new gist {}'.format(g['id']))
            commit = g['history'][0]
            version.update_config_file({
                'hash': commit['version'],
                'created_at': commit['committed_at'],
            })
            # Keep background auto-sync's merge baseline aligned so these files
            # don't look like fresh local edits on its next cycle.
            auto_sync.adopt_manual_upload(files, g)
            logger.info('upload complete')
        except gist.NotFoundError as e:
            decorators.report_gist_not_found(e)
        except Exception as e:
            decorators.report_error(self, e)

    @decorators.check_settings('access_token')
    def run(self):
        self._failed = False
        # sublime.list_packages() only works on the main thread, so take the
        # snapshot here (run() runs there) and hand it to the worker thread.
        installed = manager.installed_packages_snapshot()
        ThreadProgress(
            target=lambda: self.upload(installed),
            message='uploading files',
            success_message='files uploaded',
            success_when=lambda: not self._failed
        )
