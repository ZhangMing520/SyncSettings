# -*- coding: utf-8 -*-

import logging
import unittest

from sync_settings.libs import logger


class TestLogger(unittest.TestCase):
    def test_logger_has_file_handler(self):
        # Regression for the "empty logs" issue: the logger must have a real
        # handler attached (not rely on logging.basicConfig, which is a no-op
        # when the root logger already has handlers inside Sublime).
        self.assertTrue(len(logger.logger.handlers) > 0)
        self.assertTrue(
            any(isinstance(h, logging.FileHandler) for h in logger.logger.handlers)
        )

    def test_logger_does_not_propagate(self):
        self.assertFalse(logger.logger.propagate)
