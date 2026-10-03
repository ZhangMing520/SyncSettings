# -*- coding: utf-8 -*-

import os
import platform
from functools import wraps
from urllib.parse import unquote
from urllib.parse import quote


def separator():
    return '\\' if platform.system() == 'Windows' else '/'


def os_path(func):
    @wraps(func)
    def path_wrapper(*args, **kwargs):
        w = func(*args, **kwargs)
        sep = separator()
        return w.replace('/', sep).replace('\\', sep)
    return path_wrapper


def encode(path):
    return quote(path.replace('\\', '/'), safe='')


@os_path
def decode(path):
    return unquote(path)


def canonical(name):
    """Normalise a gist file key into this plugin's internal key space.

    Gists created by other tools may carry literal path separators
    (``sub/C.sublime-settings``), whereas this plugin stores the percent-encoded
    form (``sub%2FC.sublime-settings``). Round-tripping through ``decode`` then
    ``encode`` collapses both forms to the same key the local file scan
    produces, so the file is recognised as unchanged instead of re-synced on
    every cycle.
    """
    return encode(decode(name))


@os_path
def join(*paths):
    if not len(paths):
        return ''
    return os.path.join(*paths)


def exists(path, folder=False):
    return os.path.isdir(path) if folder else os.path.isfile(path)


def list_files(path):
    if not exists(path, folder=True):
        return []
    f = []
    for root, dirs, files in os.walk(path):
        f.extend([join(root, _file) for _file in files])
    return f
