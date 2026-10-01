# -*- coding: utf-8 -*-

import os
import zipfile

import sublime

from .libs import path, settings
from .libs.logger import logger
from . import sync_manager as manager


DEFAULT_BACKUP_NAME = 'SyncSettingsReborn.zip'


def default_backup_path():
    return settings.get('backup_path') or os.path.join(
        os.path.expanduser('~'), DEFAULT_BACKUP_NAME
    )


def preserve_packages():
    preserve = settings.get('preserve_packages')
    return True if preserve is None else bool(preserve)


def collect_files(packages_only=False):
    """Read every synced file from Packages/User as raw bytes.

    Reuses the same exclude/include + token-never-backed-up rules as the Gist
    sync. Keys are the raw (human-readable) relative path; write_user_files is
    tolerant of both raw and URL-encoded keys.
    """
    user_path = path.join(sublime.packages_path(), 'User')
    result = {}
    for f in path.list_files(user_path):
        if not manager.is_synced(f):
            continue
        if packages_only and not f.endswith('Package Control.sublime-settings'):
            continue
        rel = f.replace('{}{}'.format(user_path, path.separator()), '')
        with open(f, 'rb') as fh:
            result[rel] = fh.read()
    return result


def read_backup_zip(source_path):
    if not zipfile.is_zipfile(source_path):
        raise ValueError('not a valid backup zip: {}'.format(source_path))
    files = {}
    with zipfile.ZipFile(source_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            files[info.filename] = z.read(info.filename)
    if not files:
        raise ValueError('backup zip is empty: {}'.format(source_path))
    return files


def write_backup_zip(target_path, files):
    with zipfile.ZipFile(target_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(path.decode(name), data)


def create_backup_zip(target_path, packages_only=False):
    write_backup_zip(target_path, collect_files(packages_only=packages_only))
    logger.info('Backup written to {}'.format(target_path))


def restore_backup_zip(source_path, preserve_packages=True):
    manager.write_user_files(read_backup_zip(source_path), preserve_packages=preserve_packages)
    logger.info('Restored from {}'.format(source_path))
