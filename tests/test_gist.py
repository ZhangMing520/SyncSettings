# -*- coding: utf-8 -*-

import unittest
from unittest import mock

import requests as real_requests

from sync_settings_reborn.libs import gist


class TestRequestErrors(unittest.TestCase):
    def setUp(self):
        self.api = gist.Gist(token='token', http_proxy='', https_proxy='')

    def _mock_requests(self):
        patcher = mock.patch('sync_settings_reborn.libs.gist.requests')
        m = patcher.start()
        m.exceptions = real_requests.exceptions
        self.addCleanup(patcher.stop)
        return m

    def _response(self, status_code):
        resp = mock.Mock()
        resp.status_code = status_code
        resp.json.return_value = {'message': 'boom'}
        resp.text = 'boom'
        return resp

    def test_ssl_error_becomes_network_error(self):
        m = self._mock_requests()
        m.get.side_effect = real_requests.exceptions.SSLError('cert verify failed')
        with self.assertRaises(gist.NetworkError):
            self.api.get('gid')

    def test_connection_error_becomes_network_error(self):
        m = self._mock_requests()
        m.get.side_effect = real_requests.exceptions.ConnectionError('refused')
        with self.assertRaises(gist.NetworkError):
            self.api.get('gid')

    def test_timeout_becomes_network_error(self):
        m = self._mock_requests()
        m.get.side_effect = real_requests.exceptions.Timeout('timed out')
        with self.assertRaises(gist.NetworkError):
            self.api.get('gid')

    def test_404_becomes_not_found_error(self):
        m = self._mock_requests()
        m.get.return_value = self._response(404)
        with self.assertRaises(gist.NotFoundError):
            self.api.get('gid')

    def test_422_becomes_unprocessable_error(self):
        m = self._mock_requests()
        m.get.return_value = self._response(422)
        with self.assertRaises(gist.UnprocessableDataError):
            self.api.get('gid')

    def test_server_error_becomes_unexpected_error(self):
        m = self._mock_requests()
        m.get.return_value = self._response(500)
        with self.assertRaises(gist.UnexpectedError):
            self.api.get('gid')

    def test_ok_returns_response(self):
        m = self._mock_requests()
        resp = self._response(200)
        m.get.return_value = resp
        self.assertEqual(self.api.get('gid'), {'message': 'boom'})
