# -*- coding: utf-8 -*-

import unittest
import mock
import os
import json
import tempfile
import shutil
from sync_settings_reborn import sync_manager as manager


def create_file(file, mode='w', content=None):
    delete_file(file)
    with open(file, mode) as fi:
        if content:
            fi.write(content)


def delete_file(file):
    if os.path.isfile(file):
        os.unlink(file)


class TestSyncManager(unittest.TestCase):
    @mock.patch('sync_settings_reborn.libs.settings.get', mock.MagicMock(return_value=[
        '*Package Control.sublime-settings',
        '*.txt',
        'foo/**/*.py',
        'bar/*.py',
        'bar/*.md',
    ]))
    def test_should_exclude(self):
        tests = [
            {'file': '/usr/bin/conf/default.conf', 'expected': False},
            {'file': '/foo/bar/script.py', 'expected': False},
            {'file': 'file.js', 'expected': False},
            {'file': 'Theme.tmTheme', 'expected': False},
            {'file': 'foo/bar/file.py', 'expected': True},
            {'file': 'bar/README.md', 'expected': True},
            {'file': '/a/long/path/file.txt', 'expected': True},
            {'file': '/User/Settings/SyncSettingsReborn.sublime-settings', 'expected': True},
            {'file': '/User/Settings/Package Control.sublime-settings', 'expected': True},
        ]

        for test in tests:
            self.assertEqual(
                test['expected'],
                manager.should_exclude(test['file']),
                'comparing: {}'.format(test['file'])
            )

    @mock.patch('sync_settings_reborn.libs.settings.get', mock.MagicMock(return_value='*.txt'))
    def test_should_exclude_with_string_setting(self):
        # regression for #200: a string setting must not crash and is
        # treated as a single pattern
        self.assertTrue(manager.should_exclude('foo.txt'))
        self.assertFalse(manager.should_exclude('foo.py'))

    @mock.patch('sync_settings_reborn.libs.settings.get', mock.MagicMock(return_value='*.txt'))
    def test_should_include_with_string_setting(self):
        # regression for #200: a string setting must not crash and is
        # treated as a single pattern
        self.assertTrue(manager.should_include('foo.txt'))
        self.assertFalse(manager.should_include('foo.py'))

    @mock.patch('sync_settings_reborn.libs.settings.get', mock.MagicMock(return_value=[
        '*.sublime-settings',
        '*.txt',
    ]))
    def test_should_include(self):
        tests = [
            {'file': '/usr/bin/conf/default.conf', 'expected': False},
            {'file': '', 'expected': False},
            {'file': '/foo/bar/script.py', 'expected': False},
            {'file': 'file.js', 'expected': False},
            {'file': 'Theme.tmTheme', 'expected': False},
            {'file': 'foo/bar/file.py', 'expected': False},
            {'file': 'bar/README.md', 'expected': False},
            {'file': '/a/long/path/file.txt', 'expected': True},
            {'file': '/User/Settings/SyncSettingsReborn.sublime-settings', 'expected': False},
            {'file': '/User/Settings/Package Control.sublime-settings', 'expected': True},
        ]

        for test in tests:
            self.assertEqual(
                test['expected'],
                manager.should_include(test['file']),
                'comparing: {}'.format(test['file'])
            )

    def test_get_content(self):
        create_file('empty.txt')
        create_file('plain.txt', content='content')

        tests = [
            {'file': 'empty.txt', 'expected': ''},
            {'file': 'not-found.txt', 'expected': ''},
            {'file': 'plain.txt', 'expected': 'content'},
        ]

        for test in tests:
            self.assertEqual(manager.get_content(test['file']), test['expected'])

        delete_file('empty.txt')
        delete_file('plain.txt')

    @mock.patch('sync_settings_reborn.sync_manager.path.exists', mock.MagicMock(return_value=True))
    def test_get_content_with_exception(self):
        self.assertEqual(manager.get_content('file.error'), '')


def _settings_side_effect(ignore_dirs, excluded_files=None):
    table = {'ignore_dirs': ignore_dirs, 'excluded_files': excluded_files}
    return mock.MagicMock(side_effect=lambda key: table.get(key))


class ShouldExcludeDirsTest(unittest.TestCase):

    @mock.patch('sync_settings_reborn.sync_manager.settings.get',
                _settings_side_effect(['IgnoredDir'], None))
    def test_ignore_dirs_excludes_nested_file(self):
        self.assertTrue(manager.should_exclude('/Packages/User/IgnoredDir/foo.py'))

    @mock.patch('sync_settings_reborn.sync_manager.settings.get',
                _settings_side_effect(['IgnoredDir'], None))
    def test_ignore_dirs_keeps_other_dirs(self):
        self.assertFalse(manager.should_exclude('/Packages/User/Kept/foo.py'))

    @mock.patch('sync_settings_reborn.sync_manager.settings.get',
                _settings_side_effect(['*Cache*'], None))
    def test_ignore_dirs_with_wildcard(self):
        self.assertTrue(manager.should_exclude('/Packages/User/Foo/Cache/bar.py'))


class WriteUserFilesTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.user = os.path.join(self.tmp, 'User')
        os.makedirs(self.user)
        self.patcher = mock.patch.object(manager.sublime, 'packages_path', lambda: self.tmp)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read_pc(self):
        with open(os.path.join(self.user, 'Package Control.sublime-settings')) as f:
            return json.load(f)

    def test_write_user_files_preserves_local_packages(self):
        # incoming only has [A, B]; local already has [B, C]
        local_settings = mock.MagicMock()
        local_settings.get.return_value = ['B', 'C']
        with mock.patch.object(manager.sublime, 'load_settings', return_value=local_settings):
            manager.write_user_files(
                {'Package%20Control.sublime-settings': json.dumps(
                    {'installed_packages': ['A', 'B']}).encode()},
                preserve_packages=True,
            )
        self.assertEqual(self._read_pc()['installed_packages'], ['A', 'B', 'C'])

    def test_write_user_files_no_preserve_overwrites(self):
        local_settings = mock.MagicMock()
        local_settings.get.return_value = ['B', 'C']
        with mock.patch.object(manager.sublime, 'load_settings', return_value=local_settings):
            manager.write_user_files(
                {'Package%20Control.sublime-settings': json.dumps(
                    {'installed_packages': ['A', 'B']}).encode()},
                preserve_packages=False,
            )
        # overwrite: only the incoming list remains
        self.assertEqual(self._read_pc()['installed_packages'], ['A', 'B'])

    def test_write_user_files_writes_plain_file(self):
        manager.write_user_files({'Preferences.sublime-settings': b'{"x": 1}'}, preserve_packages=True)
        with open(os.path.join(self.user, 'Preferences.sublime-settings')) as f:
            self.assertEqual(json.load(f), {'x': 1})

    def test_write_user_files_local_packages_none(self):
        local_settings = mock.MagicMock()
        local_settings.get.return_value = None
        with mock.patch.object(manager.sublime, 'load_settings', return_value=local_settings):
            manager.write_user_files(
                {'Package%20Control.sublime-settings': json.dumps(
                    {'installed_packages': ['A', 'B']}).encode()},
                preserve_packages=True,
            )
        self.assertEqual(self._read_pc()['installed_packages'], ['A', 'B'])

    def test_write_user_files_local_packages_non_list(self):
        local_settings = mock.MagicMock()
        local_settings.get.return_value = 'not a list'
        with mock.patch.object(manager.sublime, 'load_settings', return_value=local_settings):
            manager.write_user_files(
                {'Package%20Control.sublime-settings': json.dumps(
                    {'installed_packages': ['A', 'B']}).encode()},
                preserve_packages=True,
            )
        self.assertEqual(self._read_pc()['installed_packages'], ['A', 'B'])


class FetchMoveRegressionTest(unittest.TestCase):
    """Regression tests for the Download temp-folder crash (sync.log showed
    FileNotFoundError on the temp dir in move_files)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patcher = mock.patch.object(manager.sublime, 'packages_path', lambda: self.tmp)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fetch_files_recreates_leftover_dir(self):
        # A pre-existing temp dir left behind by a prior failed run must be
        # recreated (not merely removed) so move_files can read it afterwards.
        target = os.path.join(self.tmp, 'temp')
        os.makedirs(target)
        manager.fetch_files({}, to=target)
        self.assertTrue(os.path.isdir(target))

    def test_fetch_files_idempotent(self):
        # Calling fetch_files repeatedly on the same path must not error.
        target = os.path.join(self.tmp, 'temp')
        manager.fetch_files({}, to=target)
        manager.fetch_files({}, to=target)
        self.assertTrue(os.path.isdir(target))

    def test_move_files_missing_dir_is_noop(self):
        # A missing temp dir must not raise; it used to crash with
        # FileNotFoundError inside os.listdir.
        manager.move_files(os.path.join(self.tmp, 'does-not-exist'))
