# -*- coding: utf-8 -*-

from fnmatch import fnmatch
import os
import json
import requests
import shutil
import sublime
import threading
import time

from .libs import path, settings, file
from .libs.logger import logger

from queue import Queue


def get_content(file):
    if not path.exists(file):
        return ''
    try:
        with open(file, 'rb') as fi:
            # TODO: Figure how to solve these kind of errors (for now ignore it)
            #  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x86 in position 23: invalid start byte`
            return fi.read().decode('utf-8', errors='ignore')
    except Exception as e:
        logger.warning('file `{}` has errors'.format(file))
        logger.exception(e)
    return ''


def _as_patterns(key):
    """Return `excluded_files`/`included_files` as a list of patterns.

    Users sometimes set these options to a single string instead of a list,
    which used to crash with "'str' object has no attribute 'extend'". Be
    tolerant: a string is treated as a single pattern, and we warn so the
    misconfiguration is visible instead of failing silently.
    """
    patterns = settings.get(key) or []
    if isinstance(patterns, str):
        logger.warning(
            "`{}` should be a list of patterns, but a string was given; "
            "treating it as a single pattern.".format(key)
        )
        return [patterns]
    return list(patterns)


def should_exclude(file_name):
    patterns = _as_patterns('excluded_files')
    # SyncSettingsReborn.sublime-settings is always excluded to avoid unwanted changes
    # (it holds the access_token, so it must never be backed up or restored)
    patterns.extend(['*SyncSettingsReborn.sublime-settings'])
    dir_patterns = _as_patterns('ignore_dirs')
    if dir_patterns:
        decoded = path.decode(file_name)
        parts = [p for p in decoded.split(path.separator()) if p]
        for pattern in dir_patterns:
            if any(fnmatch(part, pattern) for part in parts):
                return True
    for pattern in patterns:
        if fnmatch(file_name, pattern):
            return True
    return False


def should_include(file_name):
    patterns = _as_patterns('included_files')
    for pattern in patterns:
        if fnmatch(file_name, '*SyncSettingsReborn.sublime-settings'):
            return False
        if fnmatch(file_name, pattern):
            return True
    return False


def is_synced(file_name):
    """True when a file should be backed up / restored.

    A file is kept unless it is excluded and not explicitly included.
    """
    return not (should_exclude(file_name) and not should_include(file_name))


def get_files():
    files_with_content = dict()
    user_path = path.join(sublime.packages_path(), 'User')
    for f in path.list_files(user_path):
        encoded_path = path.encode(f.replace('{}{}'.format(user_path, path.separator()), ''))
        if encoded_path in files_with_content:
            continue
        if not is_synced(f):
            continue
        content = get_content(f)
        if not content.strip():
            continue
        files_with_content[encoded_path] = {'content': content, 'path': f}
    return files_with_content


def download_file(q):
    while not q.empty():
        url, name = q.get()
        try:
            r = requests.get(url, stream=True)
            if r.status_code == 200:
                with open(name, 'wb') as f:
                    r.raw.decode_content = True
                    shutil.copyfileobj(r.raw, f)
        except:  # noqa: E722
            pass
        finally:
            q.task_done()


def fetch_files(files, to=''):
    if not path.exists(to, folder=True):
        os.mkdir(to)
    else:
        shutil.rmtree(to, ignore_errors=True)

    rq = Queue(maxsize=0)
    user_path = path.join(sublime.packages_path(), 'User')
    items = files.items()
    for k, gfile in items:
        decoded_name = path.decode(k)
        name = path.join(user_path, decoded_name)
        if not is_synced(name):
            continue
        rq.put((gfile['raw_url'], path.join(to, k)))

    threads = min(10, len(items))
    for i in range(threads):
        worker = threading.Thread(target=download_file, args=(rq,))
        worker.setDaemon(True)
        worker.start()
        time.sleep(0.1)
    rq.join()


def _write_one(user_path, name, data):
    target = path.join(user_path, path.decode(name))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    mode = 'wb' if isinstance(data, (bytes, bytearray)) else 'w'
    with open(target, mode) as f:
        f.write(data)


def _merge_installed_packages(data):
    """Union the remote `installed_packages` with the local list so a restore
    never drops packages the user already has on this machine."""
    try:
        remote = file.encode_json(data.decode('utf-8', errors='ignore'))
    except Exception:
        return data
    if not isinstance(remote, dict):
        return data
    local_settings = sublime.load_settings('Package Control.sublime-settings')
    local_list = local_settings.get('installed_packages') or []
    remote_list = remote.get('installed_packages') or []
    if not isinstance(local_list, list):
        local_list = []
    if not isinstance(remote_list, list):
        remote_list = []
    remote['installed_packages'] = sorted(set(remote_list) | set(local_list))
    return json.dumps(remote, indent=4).encode('utf-8')


def write_user_files(files, preserve_packages=True):
    """Write collected files ({name: content}) into Packages/User.

    `Preferences`/`Package Control` files are written last. When
    `preserve_packages` is true, the incoming `Package Control.sublime-settings`
    is merged with the local `installed_packages` instead of overwriting it.
    """
    user_path = path.join(sublime.packages_path(), 'User')
    deferred = {}
    for key, data in files.items():
        name = path.decode(key)
        if name.endswith('Preferences.sublime-settings') or name.endswith('Package Control.sublime-settings'):
            deferred[key] = data
            continue
        _write_one(user_path, key, data)

    for key, data in deferred.items():
        name = path.decode(key)
        if name.endswith('Package Control.sublime-settings') and preserve_packages:
            data = _merge_installed_packages(data)
        _write_one(user_path, key, data)


def move_files(origin):
    files = {}
    for f in os.listdir(origin):
        with open(path.join(origin, f), 'rb') as fh:
            files[f] = fh.read()
    write_user_files(files, preserve_packages=True)
