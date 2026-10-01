# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
import mock
import unittest

from sync_settings_reborn import backup
from sync_settings_reborn import sync_manager as manager
from sync_settings_reborn.commands import sync_online


class BackupHelpersTest(unittest.TestCase):
    def test_default_backup_path_falls_back(self):
        with mock.patch.object(backup.settings, 'get', return_value=None):
            self.assertEqual(
                backup.default_backup_path(),
                os.path.join(os.path.expanduser('~'), 'SyncSettingsReborn.zip'),
            )

    def test_default_backup_path_uses_setting(self):
        with mock.patch.object(backup.settings, 'get', return_value='/tmp/x.zip'):
            self.assertEqual(backup.default_backup_path(), '/tmp/x.zip')

    def test_preserve_packages_default_true(self):
        with mock.patch.object(backup.settings, 'get', return_value=None):
            self.assertTrue(backup.preserve_packages())

    def test_preserve_packages_explicit(self):
        with mock.patch.object(backup.settings, 'get', return_value=False):
            self.assertFalse(backup.preserve_packages())


class SyncOnlinePullTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pull_missing_file_reports_error(self):
        cmd = sync_online.SyncSettingsRebornSyncOnlinePullCommand()
        missing = os.path.join(self.tmp, 'does-not-exist.zip')
        # report_error uses the stubbed sublime.message_dialog, so calling it is safe.
        cmd._pull(missing)
        self.assertTrue(cmd._failed)


class MoveFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.user = os.path.join(self.tmp, 'User')
        os.makedirs(self.user)
        self.patcher = mock.patch.object(manager.sublime, 'packages_path', lambda: self.tmp)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_move_files_writes_all(self):
        origin = tempfile.mkdtemp()
        try:
            with open(os.path.join(origin, 'A.sublime-settings'), 'w') as f:
                f.write('{"a": 1}')
            with open(os.path.join(origin, 'B.sublime-settings'), 'w') as f:
                f.write('{"b": 2}')
            manager.move_files(origin)
            self.assertTrue(os.path.exists(os.path.join(self.user, 'A.sublime-settings')))
            self.assertTrue(os.path.exists(os.path.join(self.user, 'B.sublime-settings')))
        finally:
            shutil.rmtree(origin, ignore_errors=True)


class IgnoreDirsMatchesDirectoriesOnlyTest(unittest.TestCase):
    """Regression: a file named like an ignored dir must not be excluded."""

    @mock.patch.object(
        manager.settings, 'get',
        mock.MagicMock(side_effect=lambda k: ['node_modules'] if k == 'ignore_dirs' else None),
    )
    def test_file_named_like_ignored_dir_kept(self):
        self.assertFalse(manager.should_exclude('/Packages/User/node_modules'))

    @mock.patch.object(
        manager.settings, 'get',
        mock.MagicMock(side_effect=lambda k: ['node_modules'] if k == 'ignore_dirs' else None),
    )
    def test_dir_named_like_ignored_dir_excluded(self):
        self.assertTrue(manager.should_exclude('/Packages/User/node_modules/foo.py'))


class ExcludedFilesBasenameTest(unittest.TestCase):
    """Regression: a bare pattern (no `*`) should match the file basename."""

    @mock.patch.object(
        manager.settings, 'get',
        mock.MagicMock(side_effect=lambda k: ['secret.txt'] if k == 'excluded_files' else None),
    )
    def test_bare_pattern_matches_basename(self):
        self.assertTrue(manager.should_exclude('/Packages/User/sub/secret.txt'))


if __name__ == '__main__':
    unittest.main()
