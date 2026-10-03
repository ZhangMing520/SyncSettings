# -*- coding: utf-8 -*-

import json
import os
import shutil
import tempfile
import zipfile
import mock
import unittest

from sync_settings_reborn import backup


def _write_user(root, rel, content):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb') as f:
        f.write(content)


def _settings_side_effect(ignore_dirs=None, excluded_files=None, included_files=None):
    table = {
        'ignore_dirs': ignore_dirs,
        'excluded_files': excluded_files,
        'included_files': included_files,
    }
    return mock.MagicMock(side_effect=lambda key: table.get(key))


class BackupZipTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.user = os.path.join(self.tmp, 'User')
        os.makedirs(self.user)
        self.patcher = mock.patch.object(backup.manager.sublime, 'packages_path', lambda: self.tmp)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _populate(self):
        _write_user(self.user, 'Preferences.sublime-settings', b'{"font_size": 12}')
        _write_user(self.user, 'SyncSettingsReborn.sublime-settings', b'{"access_token": "SECRET"}')
        _write_user(self.user, 'Package Control.sublime-settings',
                    json.dumps({'installed_packages': ['A', 'B']}).encode())
        _write_user(self.user, 'MyPackage/foo.py', b'print(1)')

    def test_backup_zip_roundtrip(self):
        self._populate()
        zip_path = os.path.join(self.tmp, 'backup.zip')
        backup.create_backup_zip(zip_path, packages_only=False)

        self.assertTrue(zipfile.is_zipfile(zip_path))
        files = backup.read_backup_zip(zip_path)
        keys = set(files.keys())
        self.assertIn('Preferences.sublime-settings', keys)
        self.assertIn('Package Control.sublime-settings', keys)
        self.assertIn('MyPackage/foo.py', keys)
        # The zip is a local, offline export: no file name is special-cased, so
        # the plugin's own settings are part of the archive like any other.
        self.assertIn('SyncSettingsReborn.sublime-settings', keys)
        self.assertEqual(files['Preferences.sublime-settings'], b'{"font_size": 12}')

    def test_backup_packages_only(self):
        self._populate()
        zip_path = os.path.join(self.tmp, 'pkgs.zip')
        backup.create_backup_zip(zip_path, packages_only=True)
        files = backup.read_backup_zip(zip_path)
        # only the package-list file survives
        self.assertEqual(set(files.keys()), {'Package Control.sublime-settings'})

    def test_restore_preserves_local_packages(self):
        # source backup with installed_packages [A, B]
        self._populate()
        zip_path = os.path.join(self.tmp, 'backup.zip')
        backup.create_backup_zip(zip_path, packages_only=False)

        # target machine already has [B, C]
        target = tempfile.mkdtemp()
        try:
            target_user = os.path.join(target, 'User')
            os.makedirs(target_user)
            _write_user(target_user, 'Package Control.sublime-settings',
                        json.dumps({'installed_packages': ['B', 'C']}).encode())

            with mock.patch.object(backup.manager.sublime, 'packages_path', lambda: target):
                # local load_settings 'Package Control.sublime-settings' returns [B, C]
                local_settings = mock.MagicMock()
                local_settings.get.return_value = ['B', 'C']
                with mock.patch.object(
                    backup.manager.sublime, 'load_settings',
                    return_value=local_settings
                ):
                    backup.restore_backup_zip(zip_path, preserve_packages=True)

            with open(os.path.join(target_user, 'Package Control.sublime-settings')) as f:
                merged = json.load(f)
            self.assertEqual(merged['installed_packages'], ['A', 'B', 'C'])
            # non-package file also restored
            self.assertTrue(os.path.exists(os.path.join(target_user, 'Preferences.sublime-settings')))
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_restore_corrupt_zip_raises(self):
        bad = os.path.join(self.tmp, 'bad.zip')
        with open(bad, 'wb') as f:
            f.write(b'not a zip')
        with self.assertRaises(ValueError):
            backup.read_backup_zip(bad)

    def test_restore_rejects_path_traversal(self):
        # A foreign/malicious zip must not be able to write outside Packages/User.
        evil = os.path.join(self.tmp, 'evil.zip')
        with zipfile.ZipFile(evil, 'w') as z:
            z.writestr('../evil.txt', b'pwned')
            z.writestr('Preferences.sublime-settings', b'{"x": 1}')
        backup.restore_backup_zip(evil, preserve_packages=False)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'evil.txt')))
        self.assertTrue(os.path.exists(os.path.join(self.user, 'Preferences.sublime-settings')))

    def test_restore_writes_back_a_token_carrying_file(self):
        # Restore is the inverse of backup: whatever the archive holds is written
        # back. Only *upload* filters tokens, because that is the only direction
        # where a secret would leave the machine. Blocking here would mean a file
        # could be backed up but never restored.
        _write_user(self.user, 'SyncSettingsReborn.sublime-settings', b'{"gist_id": "old"}')
        withzip = os.path.join(self.tmp, 'restoretoken.zip')
        with zipfile.ZipFile(withzip, 'w') as z:
            z.writestr('SyncSettingsReborn.sublime-settings', b'{"access_token": "ghp_' + b'b' * 36 + b'"}')
        backup.restore_backup_zip(withzip, preserve_packages=False)
        with open(os.path.join(self.user, 'SyncSettingsReborn.sublime-settings'), 'rb') as f:
            self.assertEqual(f.read(), b'{"access_token": "ghp_' + b'b' * 36 + b'"}')

    @mock.patch.object(backup.manager.settings, 'get', _settings_side_effect(['IgnoredDir'], None))
    def test_collect_files_respects_ignore_dirs(self):
        _write_user(self.user, 'IgnoredDir/secret.py', b'x')
        _write_user(self.user, 'Kept/ok.py', b'y')
        files = backup.collect_files()
        self.assertNotIn('IgnoredDir/secret.py', files)
        self.assertIn('Kept/ok.py', files)
