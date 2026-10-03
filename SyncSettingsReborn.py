# -*- coding: utf-8 -*-

import sys
import os

f = os.path.join(os.path.expanduser('~'), '.sync_settings_reborn')
if not os.path.isdir(f):
    os.mkdir(f)

reloader = 'sync_settings_reborn.reloader'

# Discriminate the load environment instead of catching ImportError: Sublime
# loads this module inside the `SyncSettingsReborn` package (__package__ set),
# while the test suite imports the file standalone with no parent package.
# A broad `except ImportError` would also swallow genuine errors raised inside
# the submodule graph (e.g. a missing third-party dependency) and retry the
# same failing import, masking the real cause.
if __package__:
    from .sync_settings_reborn.commands import *  # noqa: F403, F401
    from .sync_settings_reborn import auto_sync
    from .sync_settings_reborn.libs.settings import migrate_legacy

    reloader = __package__ + '.' + reloader
    # importlib.reload is the modern (3.4+) replacement for imp.reload, which
    # was removed in Python 3.12. Sublime's embedded Python is already 3.14 on
    # current builds, so fall back only for very old hosts.
    try:
        from importlib import reload
    except ImportError:
        from imp import reload

    # Make sure all dependencies are reloaded on upgrade.
    if reloader in sys.modules:
        reload(sys.modules[reloader])
else:
    from sync_settings_reborn.commands import *  # noqa: F403, F401
    from sync_settings_reborn import auto_sync
    from sync_settings_reborn.libs.settings import migrate_legacy

# Carry over config from the unmaintained original package on first run.
migrate_legacy()


def plugin_loaded():
    auto_sync.startup_sync()


def plugin_unloaded():
    auto_sync.shutdown()
