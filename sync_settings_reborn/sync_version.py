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
    except:  # noqa: E722
        pass
    return {}


def update_config_file(info):
    with open(file_path, 'w') as f:
        json.dump(info, f)
