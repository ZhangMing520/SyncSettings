import unittest
import mock
from sync_settings_reborn import sync_version as version


class TestSyncVersion(unittest.TestCase):
    @mock.patch('sync_settings_reborn.libs.path.exists', mock.MagicMock(return_value=False))
    def test_get_local_version_no_file(self):
        v = version.get_local_version()
        self.assertDictEqual({}, v)

    @mock.patch('sync_settings_reborn.libs.path.exists', mock.MagicMock(return_value=True))
    @mock.patch('sync_settings_reborn.sync_version.open', mock.mock_open(read_data='plain text'))
    def test_get_local_version_invalid_content(self):
        self.assertDictEqual({}, version.get_local_version())

    @mock.patch('sync_settings_reborn.libs.path.exists', mock.MagicMock(return_value=True))
    @mock.patch('sync_settings_reborn.sync_version.open', mock.mock_open(read_data='{}'))
    def test_get_local_version_empty_json(self):
        self.assertDictEqual({}, version.get_local_version())

    @mock.patch('sync_settings_reborn.libs.path.exists', mock.MagicMock(return_value=True))
    @mock.patch('sync_settings_reborn.sync_version.open', mock.mock_open(
        read_data='{"created_at": "2019-01-11T02:15:15Z", "hash": "123123123"}'))
    def test_get_local_version_with_content(self):
        v = version.get_local_version()
        self.assertDictEqual({'hash': '123123123', 'created_at': '2019-01-11T02:15:15Z'}, v)

    @mock.patch('sync_settings_reborn.libs.path.exists', mock.MagicMock(return_value=True))
    @mock.patch(
        'sync_settings_reborn.sync_version.open',
        mock.mock_open(
            read_data='{"created_at": "2019-01-11T02:15:15Z", /* some comment */"hash": "123123123"}'
        ),
    )
    def test_get_local_version_with_commented_content(self):
        v = version.get_local_version()
        self.assertDictEqual({"hash": "123123123", "created_at": "2019-01-11T02:15:15Z"}, v)
