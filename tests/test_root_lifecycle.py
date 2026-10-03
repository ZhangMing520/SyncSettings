# -*- coding: utf-8 -*-

"""Tests for the package-root lifecycle hooks (plugin_loaded/plugin_unloaded).

Sublime only fires these on the root module, so we import that module directly
and assert it delegates to the auto_sync daemon. The module discriminates the
load environment via ``__package__`` so it is importable both inside Sublime
and here.
"""

import unittest
import mock

import SyncSettingsReborn  # the root module (SyncSettingsReborn.py)


class RootLifecycleTest(unittest.TestCase):
    @mock.patch('sync_settings_reborn.auto_sync.startup_sync')
    def test_plugin_loaded_starts_auto_sync(self, startup_mock):
        SyncSettingsReborn.plugin_loaded()
        startup_mock.assert_called_once_with()

    @mock.patch('sync_settings_reborn.auto_sync.shutdown')
    def test_plugin_unloaded_stops_auto_sync(self, shutdown_mock):
        SyncSettingsReborn.plugin_unloaded()
        shutdown_mock.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
