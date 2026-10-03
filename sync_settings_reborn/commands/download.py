# -*- coding: utf-8 -*-

import os
import shutil

import sublime
import sublime_plugin

from . import decorators
from .. import sync_version as version, sync_manager as manager
from ..libs import settings, path, file
from ..libs.gist import Gist
from ..libs.logger import logger

from ..thread_progress import ThreadProgress


class SyncSettingsRebornDownloadCommand(sublime_plugin.WindowCommand):
    temp_folder = path.join(os.path.expanduser('~'), '.sync_settings_reborn', 'temp')

    def _local_installed_packages(self):
        try:
            local_settings = sublime.load_settings('Package Control.sublime-settings')
            local_list = local_settings.get('installed_packages') or []
            return local_list if isinstance(local_list, list) else []
        except Exception:
            return []

    def _remote_installed_packages(self):
        try:
            file_content = manager.get_content(
                path.join(self.temp_folder, path.encode('Package Control.sublime-settings'))
            )
            if not file_content:
                return []
            remote = file.encode_json(file_content)
            if not isinstance(remote, dict):
                return []
            remote_list = remote.get('installed_packages') or []
            return remote_list if isinstance(remote_list, list) else []
        except Exception as e:
            logger.warning('could not read remote installed_packages')
            logger.exception(e)
            return []

    def on_done(self, g):
        manager.move_files(self.temp_folder)
        try:
            commit = g['history'][0]
            settings.update('gist_id', g['id'])
            version.update_config_file({
                'hash': commit['version'],
                'created_at': commit['committed_at'],
            })
        except Exception as e:
            logger.warning('could not update gist metadata')
            logger.exception(e)
        shutil.rmtree(self.temp_folder, ignore_errors=True)

    def download(self):
        try:
            g = Gist(
                token=settings.get('access_token'),
                http_proxy=settings.get('http_proxy'),
                https_proxy=settings.get('https_proxy')
            ).get(settings.get('gist_id'))
            files = g.get('files') or {}
            if not files:
                logger.warning('The gist `{}` contains no files.'.format(settings.get('gist_id')))
                sublime.status_message('SyncSettingsReborn: the gist is empty or not found')
                self._failed = True
                return

            manager.fetch_files(files, self.temp_folder)

            # Restore the user files first. This is the primary goal and must
            # always happen, independent of the package-install step below.
            self.on_done(g)

            # Best-effort: install any packages present remotely but missing
            # locally. Wrapped so a failure here can never block the file
            # restore above.
            try:
                remote_list = self._remote_installed_packages()
                diff = set(remote_list).difference(set(self._local_installed_packages()))
                if len(diff) > 0:
                    self.window.run_command('advanced_install_package', {'packages': list(diff)})
            except Exception as e:
                logger.warning('skipping package installation')
                logger.exception(e)
        except Exception as e:
            decorators.report_error(self, e)

    @decorators.check_settings('gist_id')
    def run(self):
        self._failed = False
        ThreadProgress(
            target=self.download,
            message='downloading files',
            success_message='files downloaded',
            success_when=lambda: not self._failed
        )
