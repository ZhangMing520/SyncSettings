# -*- coding: utf-8 -*-

import sublime
import sys
import os

f = os.path.join(os.path.expanduser('~'), '.sync_settings_reborn')
if not os.path.isdir(f):
    os.mkdir(f)

reloader = 'sync_settings_reborn.reloader'

if int(sublime.version()) > 3000:
    from .sync_settings_reborn.commands import *  # noqa: F403, F401

    reloader = 'SyncSettingsReborn.' + reloader
    from imp import reload
else:
    from sync_settings_reborn.commands import *  # noqa: F403, F401

# Make sure all dependencies are reloaded on upgrade
if reloader in sys.modules:
    reload(sys.modules[reloader])

# Imported AFTER the reloader so a package reload binds the freshly reloaded
# auto_sync module. Sublime only invokes plugin_loaded/plugin_unloaded on
# modules in the package root, so the lifecycle hooks live here and delegate.
if int(sublime.version()) > 3000:
    from .sync_settings_reborn import auto_sync
else:
    from sync_settings_reborn import auto_sync

# Carry over config from the unmaintained original package on first run.
from .sync_settings_reborn.libs.settings import migrate_legacy
migrate_legacy()


def plugin_loaded():
    auto_sync.startup_sync()


def plugin_unloaded():
    auto_sync.shutdown()
