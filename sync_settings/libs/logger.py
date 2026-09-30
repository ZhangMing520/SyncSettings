# -*- coding: utf-8 -*-

import logging
import os
from os import path

log_dir = path.join(path.expanduser('~'), '.sync_settings')
log_file = path.join(log_dir, 'sync.log')

# Make sure the directory exists so the file handler can be created even if the
# plugin host hasn't created it yet.
os.makedirs(log_dir, exist_ok=True)

logger = logging.getLogger('SyncSettings')
logger.setLevel(logging.DEBUG)

# Attach a file handler explicitly instead of relying on logging.basicConfig.
# basicConfig is a no-op when the root logger already has handlers, which is the
# normal case inside Sublime's plugin host. Without this, warnings/exceptions
# were silently dropped and the log file stayed empty.
if not logger.handlers:
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s: %(message)s'
    ))
    logger.addHandler(file_handler)

# Don't propagate to the root logger, otherwise records can be duplicated or
# lost when other packages have configured the root logger.
logger.propagate = False
