# -*- coding: utf-8 -*

import json
import os
from .libs import path, file

file_path = path.join(os.path.expanduser('~'), '.sync_settings_reborn', 'sync.json')


def get_local_version():
    if not path.exists(file_path):
        return {}
    try:
        with open(file_path) as f:
            return file.encode_json(f.read())
    except Exception:
        pass
    return {}


def update_config_file(info):
    # Write to a sibling temp file and atomically os.replace, so a crash or the
    # host exiting mid-write can never leave a truncated sync.json (which the
    # next load would silently treat as an empty baseline).
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    tmp = file_path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(info, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, file_path)
