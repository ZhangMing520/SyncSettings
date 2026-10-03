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


def _is_token(file_name):
    """True for the file that holds the Gist access_token.

    Compared case-insensitively so the token can never be backed up or restored
    on any platform (fnmatch is case-sensitive on Linux).
    """
    return os.path.basename(file_name).lower() == settings.filename.lower()


def should_exclude(file_name):
    if _is_token(file_name):
        return True
    basename = os.path.basename(file_name)
    patterns = _as_patterns('excluded_files')
    dir_patterns = _as_patterns('ignore_dirs')
    if dir_patterns:
        decoded = path.decode(file_name)
        # Match only directory components, never the file name itself, so a file
        # coincidentally named like an ignored directory is not excluded.
        dir_parts = [p for p in decoded.split(path.separator()) if p][:-1]
        for pattern in dir_patterns:
            if any(fnmatch(part, pattern) for part in dir_parts):
                return True
    return _matches(patterns, file_name, basename)


def _matches(patterns, name, basename):
    return any(fnmatch(name, p) or fnmatch(basename, p) for p in patterns)


def should_include(file_name):
    if _is_token(file_name):
        return False
    basename = os.path.basename(file_name)
    patterns = _as_patterns('included_files')
    return _matches(patterns, file_name, basename)


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
    # Always (re)create the destination so a leftover temp folder from a prior
    # failed run can never cause `move_files` to fail with a missing directory.
    if path.exists(to, folder=True):
        shutil.rmtree(to, ignore_errors=True)
    os.makedirs(to, exist_ok=True)

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


def _is_within(user_real, target):
    target_real = os.path.realpath(target)
    return target_real == user_real or target_real.startswith(user_real + os.sep)


def _write_one(user_path, user_real, name, data):
    target = path.join(user_path, path.decode(name))
    # Guard against path traversal (e.g. a zip entry like `../../.bashrc`): never
    # write outside Packages/User, even for foreign or malicious backups.
    if not _is_within(user_real, target):
        logger.warning('refusing to write outside Packages/User: {}'.format(target))
        return
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
    user_real = os.path.realpath(user_path)
    deferred = {}
    for key, data in files.items():
        name = path.decode(key)
        # Defense in depth: never let a foreign backup clobber the access token.
        if _is_token(name):
            logger.warning('skipping token file in backup: {}'.format(name))
            continue
        if name.endswith('Preferences.sublime-settings') or name.endswith('Package Control.sublime-settings'):
            deferred[key] = data
            continue
        _write_one(user_path, user_real, key, data)

    for key, data in deferred.items():
        name = path.decode(key)
        if name.endswith('Package Control.sublime-settings') and preserve_packages:
            data = _merge_installed_packages(data)
        _write_one(user_path, user_real, key, data)


def move_files(origin):
    if not path.exists(origin, folder=True):
        logger.warning('download temp folder is missing, nothing to restore: {}'.format(origin))
        return
    files = {}
    for f in os.listdir(origin):
        with open(path.join(origin, f), 'rb') as fh:
            files[f] = fh.read()
    write_user_files(files, preserve_packages=True)
