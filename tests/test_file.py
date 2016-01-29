﻿# coding: utf-8

#-------------------------------------------------------------------------
# Copyright (c) Microsoft.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#--------------------------------------------------------------------------
import base64
import os
import requests
import sys
import unittest
from datetime import datetime, timedelta
from azure.common import (
    AzureHttpError,
    AzureMissingResourceHttpError,
)
from azure.storage import (
    AccessPolicy,
    ResourceTypes,
    AccountPermissions,
)
from azure.storage.file import (
    FileService,
    File,
    FileService,
    ContentSettings,
    FilePermissions,
)
from tests.testcase import (
    StorageTestCase,
    TestMode,
    record,
)

#------------------------------------------------------------------------------
TEST_SHARE_PREFIX = 'share'
TEST_DIRECTORY_PREFIX = 'dir'
TEST_FILE_PREFIX = 'file'
INPUT_FILE_PATH = 'file_input.temp.dat'
OUTPUT_FILE_PATH = 'file_output.temp.dat'
#------------------------------------------------------------------------------

class StorageFileTest(StorageTestCase):

    def setUp(self):
        super(StorageFileTest, self).setUp()

        self.fs = self._create_storage_service(FileService, self.settings)

        # test chunking functionality by reducing the threshold
        # for chunking and the size of each chunk, otherwise
        # the tests would take too long to execute
        self.fs._FILE_MAX_DATA_SIZE = 64 * 1024
        self.fs._FILE_MAX_CHUNK_DATA_SIZE = 4 * 1024

        self.share_name = self.get_resource_name('utshare')

        if not self.is_playback():
            self.fs.create_share(self.share_name)

        self.short_byte_data = self.get_random_bytes(1024)

        if self.settings.REMOTE_STORAGE_ACCOUNT_NAME and self.settings.REMOTE_STORAGE_ACCOUNT_KEY:
            self.fs2 = self._create_storage_service(
                FileService,
                self.settings,
                self.settings.REMOTE_STORAGE_ACCOUNT_NAME,
                self.settings.REMOTE_STORAGE_ACCOUNT_KEY,
            )
            self.remote_share_name = None
        else:
            print("REMOTE_STORAGE_ACCOUNT_NAME and REMOTE_STORAGE_ACCOUNT_KEY not set in test settings file.")

    def tearDown(self):
        if not self.is_playback():
            try:
                self.fs.delete_share(self.share_name)
            except:
                pass

            if self.remote_share_name:
                try:
                    self.fs2.delete_share(self.remote_share_name)
                except:
                    pass

        if os.path.isfile(INPUT_FILE_PATH):
            try:
                os.remove(INPUT_FILE_PATH)
            except:
                pass

        if os.path.isfile(OUTPUT_FILE_PATH):
            try:
                os.remove(OUTPUT_FILE_PATH)
            except:
                pass

        return super(StorageFileTest, self).tearDown()

    #--Helpers-----------------------------------------------------------------
    def _get_file_reference(self):
        return self.get_resource_name(TEST_FILE_PREFIX)

    def _create_file(self):
        file_name = self._get_file_reference()
        self.fs.create_file_from_bytes(self.share_name, None, file_name, self.short_byte_data)
        return file_name

    def _create_remote_share(self):
        self.remote_share_name = self.get_resource_name('remoteshare')
        self.fs2.create_share(self.remote_share_name)

    def _create_remote_file(self, file_data=None):
        if not file_data:
            file_data = b'12345678' * 1024 * 1024
        source_file_name = self._get_file_reference()
        self.fs2.create_file_from_bytes(self.remote_share_name, None, source_file_name, file_data)
        return source_file_name

    def _wait_for_async_copy(self, share_name, dir_name, file_name):
        count = 0
        file = self.fs.get_file_properties(share_name, dir_name, file_name)
        while file.properties.copy.status != 'success':
            count = count + 1
            if count > 5:
                self.assertTrue(
                    False, 'Timed out waiting for async copy to complete.')
            self.sleep(5)
            file = self.fs.get_file_properties(share_name, dir_name, file_name)
        self.assertEqual(file.properties.copy.status, 'success')

    def assertFileEqual(self, share_name, dir_name, file_name, expected_data):
        actual_data = self.fs.get_file_to_bytes(share_name, dir_name, file_name)
        self.assertEqual(actual_data.content, expected_data)

    def _get_expected_upload_progress(self, file_size, unknown_size=True):
        result = []
        index = 0
        total = None if unknown_size else file_size
        while (index < file_size):
            result.append((index, total))
            index += self.fs._FILE_MAX_CHUNK_DATA_SIZE
        result.append((file_size, total))
        return result

    def _get_expected_download_progress(self, file_size, single_download=True):
        result = []
        index = 0
        if single_download:
            result.append((0, None))
        else:
            while (index < file_size):
                result.append((index, file_size))
                index += self.fs._FILE_MAX_CHUNK_DATA_SIZE
        result.append((file_size, file_size))
        return result

    class NonSeekableFile(object):
        def __init__(self, wrapped_file):
            self.wrapped_file = wrapped_file

        def write(self, data):
            self.wrapped_file.write(data)

        def read(self, count):
            return self.wrapped_file.read(count)

    #--Test cases for files ----------------------------------------------
    @record
    def test_make_file_url(self):
        # Arrange

        # Act
        res = self.fs.make_file_url('vhds', 'vhd_dir', 'my.vhd')

        # Assert
        self.assertEqual(res, 'https://' + self.settings.STORAGE_ACCOUNT_NAME
                         + '.file.core.windows.net/vhds/vhd_dir/my.vhd')

    @record
    def test_make_file_url_no_directory(self):
        # Arrange

        # Act
        res = self.fs.make_file_url('vhds', None, 'my.vhd')

        # Assert
        self.assertEqual(res, 'https://' + self.settings.STORAGE_ACCOUNT_NAME
                         + '.file.core.windows.net/vhds/my.vhd')

    @record
    def test_make_file_url_with_protocol(self):
        # Arrange

        # Act
        res = self.fs.make_file_url('vhds', 'vhd_dir', 'my.vhd', protocol='http')

        # Assert
        self.assertEqual(res, 'http://' + self.settings.STORAGE_ACCOUNT_NAME
                         + '.file.core.windows.net/vhds/vhd_dir/my.vhd')

    @record
    def test_make_file_url_with_sas(self):
        # Arrange

        # Act
        res = self.fs.make_file_url(
            'vhds', 'vhd_dir', 'my.vhd', sas_token='sas')

        # Assert
        self.assertEqual(res, 'https://' + self.settings.STORAGE_ACCOUNT_NAME + 
                         '.file.core.windows.net/vhds/vhd_dir/my.vhd?sas')

    @record
    def test_create_file(self):
        # Arrange
        file_name = self._get_file_reference()

        # Act
        self.fs.create_file(self.share_name, None, file_name, 1024)

        # Assert
        self.fs.exists(self.share_name, None, file_name)

    @record
    def test_create_file_with_metadata(self):
        # Arrange
        metadata={'hello': 'world', 'number': '42'}
        file_name = self._get_file_reference()

        # Act
        self.fs.create_file(self.share_name, None, file_name, 1024, metadata=metadata)

        # Assert
        md = self.fs.get_file_metadata(self.share_name, None, file_name)
        self.assertDictEqual(md, metadata)

    @record
    def test_file_exists(self):
        # Arrange
        file_name = self._create_file()

        # Act
        exists = self.fs.exists(self.share_name, None, file_name)

        # Assert
        self.assertTrue(exists)

    @record
    def test_file_not_exists(self):
        # Arrange
        file_name = self._get_file_reference()

        # Act
        exists = self.fs.exists(self.share_name, 'missingdir', file_name)

        # Assert
        self.assertFalse(exists)

    @record
    def test_get_file_with_existing_file(self):
        # Arrange
        file_name = self._create_file()

        # Act
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name)

        # Assert
        self.assertIsInstance(file, File)
        self.assertEqual(file.content, self.short_byte_data)

    @record
    def test_get_file_with_range(self):
        # Arrange
        file_name = self._create_file()

        # Act
        file = self.fs.get_file_to_bytes(
            self.share_name, None, file_name, start_range=0, end_range=5)

        # Assert
        self.assertIsInstance(file, File)
        self.assertEqual(file.content, self.short_byte_data[0:6])

    @record
    def test_get_file_with_range_and_get_content_md5(self):
        # Arrange
        file_name = self._create_file()

        # Act
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name,
                                 start_range=0, end_range=5,
                                 range_get_content_md5=True)

        # Assert
        self.assertIsInstance(file, File)
        self.assertEqual(file.content, self.short_byte_data[0:6])
        self.assertIsNotNone(file.properties.content_settings.content_md5)

    @record
    def test_get_file_with_non_existing_file(self):
        # Arrange
        file_name = self._get_file_reference()

        # Act
        with self.assertRaises(AzureMissingResourceHttpError):
            self.fs.get_file_to_bytes(self.share_name, None, file_name)

        # Assert
        
    @record
    def test_resize_file(self):
        # Arrange
        file_name = self._create_file()

        # Act
        self.fs.resize_file(self.share_name, None, file_name, 5)

        # Assert
        file = self.fs.get_file_properties(self.share_name, None, file_name)
        self.assertEqual(file.properties.content_length, 5)

    @record
    def test_set_file_properties(self):
        # Arrange
        file_name = self._create_file()

        # Act
        content_settings=ContentSettings(
            content_language='spanish',
            content_disposition='inline')
        resp = self.fs.set_file_properties(
            self.share_name,
            None, 
            file_name,
            content_settings=content_settings
        )

        # Assert
        properties = self.fs.get_file_properties(self.share_name, None, file_name).properties
        self.assertEqual(properties.content_settings.content_language, content_settings.content_language)
        self.assertEqual(properties.content_settings.content_disposition, content_settings.content_disposition)

    @record
    def test_get_file_properties(self):
        # Arrange
        file_name = self._create_file()

        # Act
        file = self.fs.get_file_properties(self.share_name, None, file_name)

        # Assert
        self.assertIsNotNone(file)
        self.assertEqual(file.properties.content_length, len(self.short_byte_data))

    @record
    def test_get_file_properties_with_non_existing_file(self):
        # Arrange
        file_name = self._get_file_reference()

        # Act
        with self.assertRaises(AzureMissingResourceHttpError):
            self.fs.get_file_properties(self.share_name, None, file_name)

        # Assert

    @record
    def test_get_file_metadata(self):
        # Arrange
        file_name = self._create_file()

        # Act
        md = self.fs.get_file_metadata(self.share_name, None, file_name)

        # Assert
        self.assertIsNotNone(md)
        self.assertEqual(0, len(md))

    @record
    def test_set_file_metadata_with_upper_case(self):
        # Arrange
        metadata = {'hello': 'world', 'number': '42', 'UP': 'UPval'}
        file_name = self._create_file()

        # Act
        self.fs.set_file_metadata(self.share_name, None, file_name, metadata)

        # Assert
        md = self.fs.get_file_metadata(self.share_name, None, file_name)
        self.assertEqual(3, len(md))
        self.assertEqual(md['hello'], 'world')
        self.assertEqual(md['number'], '42')
        self.assertEqual(md['up'], 'UPval')

    @record
    def test_delete_file_with_existing_file(self):
        # Arrange
        file_name = self._create_file()

        # Act
        self.fs.delete_file(self.share_name, None, file_name)

        # Assert
        self.assertFalse(self.fs.exists(self.share_name, None, file_name))

    @record
    def test_delete_file_with_non_existing_file(self):
        # Arrange
        file_name = self._get_file_reference()

        # Act
        with self.assertRaises(AzureMissingResourceHttpError):
            self.fs.delete_file (self.share_name, None, file_name)

        # Assert

    @record
    def test_update_file(self):
        # Arrange
        file_name = self._create_file()

        # Act
        data = b'abcdefghijklmnop' * 32
        self.fs.update_range(self.share_name, None, file_name, data, 0, 511)

        # Assert
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name)
        self.assertEqual(data, file.content[:512])
        self.assertEqual(self.short_byte_data[512:], file.content[512:])

    @record
    def test_clear_file(self):
        # Arrange
        file_name = self._create_file()

        # Act
        resp = self.fs.clear_range(self.share_name, None, file_name, 0, 511)

        # Assert
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name)
        self.assertEqual(b'\x00' * 512, file.content[:512])
        self.assertEqual(self.short_byte_data[512:], file.content[512:])

    @record
    def test_update_file_unicode(self):
        # Arrange
        file_name = self._create_file()

        # Act
        data = u'abcdefghijklmnop' * 32
        with self.assertRaises(TypeError):
            self.fs.update_range(self.share_name, None, file_name,
                             data, 0, 511)

        # Assert

    @record
    def test_list_ranges_none(self):
        # Arrange
        file_name = self._get_file_reference()
        self.fs.create_file(self.share_name, None, file_name, 1024)

        # Act
        ranges = self.fs.list_ranges(self.share_name, None, file_name)

        # Assert
        self.assertIsNotNone(ranges)
        self.assertEqual(len(ranges), 0)

    @record
    def test_list_ranges_2(self):
        # Arrange
        file_name = self._get_file_reference()
        self.fs.create_file(self.share_name, None, file_name, 2048)

        data = b'abcdefghijklmnop' * 32
        resp1 = self.fs.update_range(self.share_name, None, file_name, data, 0, 511)
        resp2 = self.fs.update_range(self.share_name, None, file_name, data, 1024, 1535)

        # Act
        ranges = self.fs.list_ranges(self.share_name, None, file_name)

        # Assert
        self.assertIsNotNone(ranges)
        self.assertEqual(len(ranges), 2)
        self.assertEqual(ranges[0].start, 0)
        self.assertEqual(ranges[0].end, 511)
        self.assertEqual(ranges[1].start, 1024)
        self.assertEqual(ranges[1].end, 1535)

    @record
    def test_copy_file_with_existing_file(self):
        # Arrange
        file_name = self._create_file()

        # Act
        sourcefile = self.fs.make_file_url(self.share_name, None, file_name)
        copy = self.fs.copy_file(self.share_name, None, 'file1copy', sourcefile)

        # Assert
        self.assertIsNotNone(copy)
        self.assertEqual(copy.status, 'success')
        self.assertIsNotNone(copy.id)
        copy_file = self.fs.get_file_to_bytes(self.share_name, None, 'file1copy')
        self.assertEqual(copy_file.content, self.short_byte_data)

    @record
    def test_copy_file_async_private_file(self):
        # Arrange
        self._create_remote_share()
        source_file_name = self._create_remote_file()
        source_file_url = self.fs2.make_file_url(self.remote_share_name, None, source_file_name)

        # Act
        target_file_name = 'targetfile'
        with self.assertRaises(AzureMissingResourceHttpError):
            self.fs.copy_file(self.share_name, None, target_file_name, source_file_url)

        # Assert

    @record
    def test_copy_file_async_private_file_with_sas(self):
        # Arrange
        data = b'12345678' * 1024 * 1024
        self._create_remote_share()
        source_file_name = self._create_remote_file(file_data=data)

        sas_token = self.fs2.generate_file_shared_access_signature(
            self.remote_share_name,
            None,
            source_file_name,
            permission=FilePermissions.READ,
            expiry=datetime.utcnow() + timedelta(hours=1),          
        )

        source_file_url = self.fs2.make_file_url(
            self.remote_share_name,
            None,
            source_file_name,
            sas_token=sas_token,
        )

        # Act
        target_file_name = 'targetfile'
        copy_resp = self.fs.copy_file(self.share_name, None, target_file_name, source_file_url)

        # Assert
        self.assertEqual(copy_resp.status, 'pending')
        self._wait_for_async_copy(self.share_name, None, target_file_name)
        actual_data = self.fs.get_file_to_bytes(self.share_name, None, target_file_name)
        self.assertEqual(actual_data.content, data)

    @record
    def test_abort_copy_file(self):
        # Arrange
        data = b'12345678' * 1024 * 1024
        self._create_remote_share()
        source_file_name = self._create_remote_file(file_data=data)

        sas_token = self.fs2.generate_file_shared_access_signature(
            self.remote_share_name,
            None,
            source_file_name,
            permission=FilePermissions.READ,
            expiry=datetime.utcnow() + timedelta(hours=1),          
        )

        source_file_url = self.fs2.make_file_url(
            self.remote_share_name,
            None,
            source_file_name,
            sas_token=sas_token,
        )

        # Act
        target_file_name = 'targetfile'
        copy_resp = self.fs.copy_file(self.share_name, None, target_file_name, source_file_url)
        self.assertEqual(copy_resp.status, 'pending')
        self.fs.abort_copy_file(self.share_name, None, 'targetfile', copy_resp.id)

        # Assert
        target_file = self.fs.get_file_to_bytes(self.share_name, None, target_file_name)
        self.assertEqual(target_file.content, b'')
        self.assertEqual(target_file.properties.copy.status, 'aborted')

    @record
    def test_abort_copy_file_with_synchronous_copy_fails(self):
        # Arrange
        source_file_name = self._create_file()
        source_file_url = self.fs.make_file_url(self.share_name, None, source_file_name)

        # Act
        target_file_name = 'targetfile'
        copy_resp = self.fs.copy_file(self.share_name, None, target_file_name, source_file_url)
        with self.assertRaises(AzureHttpError):
            self.fs.abort_copy_file(
                self.share_name,
                None, 
                target_file_name,
                copy_resp.id)

        # Assert
        self.assertEqual(copy_resp.status, 'success')

    @record
    def test_with_filter(self):
        # Single filter
        if sys.version_info < (3,):
            strtype = (str, unicode)
            strornonetype = (str, unicode, type(None))
        else:
            strtype = str
            strornonetype = (str, type(None))

        called = []

        def my_filter(request, next):
            called.append(True)
            for header in request.headers:
                self.assertIsInstance(header, tuple)
                for item in header:
                    self.assertIsInstance(item, strornonetype)
            self.assertIsInstance(request.host, strtype)
            self.assertIsInstance(request.method, strtype)
            self.assertIsInstance(request.path, strtype)
            self.assertIsInstance(request.query, list)
            self.assertIsInstance(request.body, strtype)
            response = next(request)

            self.assertIsInstance(response.body, (bytes, type(None)))
            self.assertIsInstance(response.headers, list)
            for header in response.headers:
                self.assertIsInstance(header, tuple)
                for item in header:
                    self.assertIsInstance(item, strtype)
            self.assertIsInstance(response.status, int)
            return response

        bc = self.fs.with_filter(my_filter)
        bc.create_share(self.share_name + '0', fail_on_exist=False)

        self.assertTrue(called)

        del called[:]

        bc.delete_share(self.share_name + '0')

        self.assertTrue(called)
        del called[:]

        # Chained filters
        def filter_a(request, next):
            called.append('a')
            return next(request)

        def filter_b(request, next):
            called.append('b')
            return next(request)

        bc = self.fs.with_filter(filter_a).with_filter(filter_b)
        bc.create_share(self.share_name + '1', fail_on_exist=False)

        self.assertEqual(called, ['b', 'a'])

        bc.delete_share(self.share_name + '1')

        self.assertEqual(called, ['b', 'a', 'b', 'a'])

    @record
    def test_unicode_get_file_unicode_name(self):
        # Arrange
        file_name = '啊齄丂狛狜'
        self.fs.create_file_from_bytes(self.share_name, None, file_name, b'hello world')

        # Act
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name)

        # Assert
        self.assertIsInstance(file, File)
        self.assertEqual(file.content, b'hello world')

    @record
    def test_file_unicode_data(self):
        # Arrange
        file_name = self._get_file_reference()

        # Act
        data = u'hello world啊齄丂狛狜'.encode('utf-8')
        self.fs.create_file_from_bytes (self.share_name, None, file_name, data)

        # Assert
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name)
        self.assertIsInstance(file, File)
        self.assertEqual(file.content, data)

    @record
    def test_unicode_get_file_binary_data(self):
        # Arrange
        base64_data = 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P3+/wABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj9AQUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVpbXF1eX2BhYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ent8fX5/gIGCg4SFhoeIiYqLjI2Oj5CRkpOUlZaXmJmam5ydnp+goaKjpKWmp6ipqqusra6vsLGys7S1tre4ubq7vL2+v8DBwsPExcbHyMnKy8zNzs/Q0dLT1NXW19jZ2tvc3d7f4OHi4+Tl5ufo6err7O3u7/Dx8vP09fb3+Pn6+/z9/v8AAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4/QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl9gYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXp7fH1+f4CBgoOEhYaHiImKi4yNjo+QkZKTlJWWl5iZmpucnZ6foKGio6SlpqeoqaqrrK2ur7CxsrO0tba3uLm6u7y9vr/AwcLDxMXGx8jJysvMzc7P0NHS09TV1tfY2drb3N3e3+Dh4uPk5ebn6Onq6+zt7u/w8fLz9PX29/j5+vv8/f7/AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P3+/w=='       
        binary_data = base64.b64decode(base64_data)

        file_name = self._get_file_reference()
        self.fs.create_file_from_bytes(self.share_name, None, file_name, binary_data)

        # Act
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name)

        # Assert
        self.assertIsInstance(file, File)
        self.assertEqual(file.content, binary_data)

    @record
    def test_get_file_to_bytes(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE - 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_bytes(self.share_name, None, input_file)

        # Assert
        self.assertEqual(data, file.content)

    def test_get_file_to_bytes_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_bytes(self.share_name, None, input_file, max_connections=2)

        # Assert
        self.assertEqual(data, file.content)

    @record
    def test_get_file_to_bytes_with_progress(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE - 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file = self.fs.get_file_to_bytes(self.share_name, None, input_file, progress_callback=callback)

        # Assert
        self.assertEqual(data, file.content)
        self.assertEqual(self._get_expected_download_progress(len(data)), progress)

    @record
    def test_get_file_to_bytes_with_progress_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file = self.fs.get_file_to_bytes(self.share_name, None, input_file, progress_callback=callback, max_connections=2)

        # Assert
        self.assertEqual(data, file.content)
        self.assertEqual(self._get_expected_download_progress(len(data), False), progress)

    @record
    def test_get_file_to_stream(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE - 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            file = self.fs.get_file_to_stream(
                self.share_name, None, input_file, stream)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)

    def test_get_file_to_stream_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            file = self.fs.get_file_to_stream(
                self.share_name, None, input_file, stream, max_connections=2)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)

    def test_get_file_to_stream_non_seekable(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            non_seekable_stream = StorageFileTest.NonSeekableFile(stream)
            file = self.fs.get_file_to_stream(self.share_name, None, input_file, non_seekable_stream)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)

    def test_get_file_to_stream_non_seekable_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            non_seekable_stream = StorageFileTest.NonSeekableFile(stream)

            with self.assertRaises(BaseException):
                file = self.fs.get_file_to_stream(
                    self.share_name, None, input_file, non_seekable_stream, max_connections=2)

        # Assert

    @record
    def test_get_file_to_stream_with_progress(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            file = self.fs.get_file_to_stream(
                self.share_name, None, input_file, stream, progress_callback=callback)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)
        self.assertEqual(self._get_expected_download_progress(len(data)), progress)

    def test_get_file_to_stream_with_progress_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            file = self.fs.get_file_to_stream(
                self.share_name, None, input_file, stream,
                progress_callback=callback,
                max_connections=5)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)
        self.assertEqual(self._get_expected_download_progress(len(data), False), progress)

    @record
    def test_get_file_to_path(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_path(self.share_name, None, input_file, OUTPUT_FILE_PATH)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)

    def test_get_file_to_path_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_path(
            self.share_name, None, input_file, OUTPUT_FILE_PATH, max_connections=5)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)

    def test_ranged_get_file_to_path(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_path(
            self.share_name, None, input_file, OUTPUT_FILE_PATH, start_range=1, end_range=3,
            range_get_content_md5=True, max_connections=5)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data[1:4], actual)

    def test_ranged_get_file_to_path_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_path(
            self.share_name, None, input_file, OUTPUT_FILE_PATH, start_range=0,
            max_connections=5)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)

    def test_ranged_get_file_to_path_md5_without_end_range_fail(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        with self.assertRaises(ValueError):
            file = self.fs.get_file_to_path(
                self.share_name, None, input_file, OUTPUT_FILE_PATH, start_range=1,
                range_get_content_md5=True, max_connections=5)

        # Assert

    @record
    def test_get_file_to_path_with_progress(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file = self.fs.get_file_to_path(
            self.share_name, None, input_file, OUTPUT_FILE_PATH, progress_callback=callback)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)
        self.assertEqual(self._get_expected_download_progress(len(data)), progress)

    @record
    def test_get_file_to_path_with_progress_parallel(self):
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file = self.fs.get_file_to_path(
            self.share_name, None, input_file, OUTPUT_FILE_PATH,
            progress_callback=callback, max_connections=2)

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(data, actual)
        self.assertEqual(self._get_expected_download_progress(len(data), False), progress)

    @record
    def test_get_file_to_path_with_mode(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)
        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            stream.write(b'abcdef')

        # Act
        file = self.fs.get_file_to_path(
            self.share_name, None, input_file, OUTPUT_FILE_PATH, 'a+b')

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(b'abcdef' + data, actual)

    @record
    def test_get_file_to_path_with_mode_parallel(self):
        # Arrange
        input_file = self.get_resource_name('bytefile')
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_bytes(self.share_name, None, input_file, data)
        with open(OUTPUT_FILE_PATH, 'wb') as stream:
            stream.write(b'abcdef')

        # Act
        file = self.fs.get_file_to_path(
            self.share_name, None, input_file, OUTPUT_FILE_PATH, 'a+b')

        # Assert
        self.assertIsInstance(file, File)
        with open(OUTPUT_FILE_PATH, 'rb') as stream:
            actual = stream.read()
            self.assertEqual(b'abcdef' + data, actual)

    @record
    def test_get_file_to_text(self):
        # Arrange
        input_file = self.get_resource_name('textfile')
        data = self.get_random_text_data(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_text(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_text(self.share_name, None, input_file)

        # Assert
        self.assertEqual(data, file.content)

    def test_get_file_to_text_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        input_file = self.get_resource_name('textfile')
        data = self.get_random_text_data(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_text(self.share_name, None, input_file, data)

        # Act
        file = self.fs.get_file_to_text(self.share_name, None, input_file, max_connections=5)

        # Assert
        self.assertEqual(data, file.content)

    @record
    def test_get_file_to_text_with_progress(self):
        # Arrange
        input_file = self.get_resource_name('textfile')
        data = self.get_random_text_data(self.fs._FILE_MAX_DATA_SIZE + 512)
        self.fs.create_file_from_text(self.share_name, None, input_file, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file = self.fs.get_file_to_text(
            self.share_name, None, input_file, progress_callback=callback)

        # Assert
        self.assertEqual(data, file.content)
        self.assertEqual(self._get_expected_download_progress(len(data.encode('utf-8'))), progress)

    @record
    def test_get_file_to_text_with_encoding(self):
        # Arrange
        text = u'hello 啊齄丂狛狜 world'
        data = text.encode('utf-16')
        file_name = self._get_file_reference()
        self.fs.create_file_from_bytes(self.share_name, None, file_name, data)

        # Act
        file = self.fs.get_file_to_text(self.share_name, None, file_name, 'utf-16')

        # Assert
        self.assertEqual(text, file.content)

    @record
    def test_get_file_to_text_with_encoding_and_progress(self):
        # Arrange
        text = u'hello 啊齄丂狛狜 world'
        data = text.encode('utf-16')
        file_name = self._get_file_reference()
        self.fs.create_file_from_bytes(self.share_name, None, file_name, data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file = self.fs.get_file_to_text(
            self.share_name, None, file_name, 'utf-16', progress_callback=callback)

        # Assert
        self.assertEqual(text, file.content)
        self.assertEqual(self._get_expected_download_progress(len(data)), progress)

    @record
    def test_create_file_from_bytes_with_progress(self):
        # Arrange
        file_name = self._get_file_reference()
        data = self.get_random_bytes(2048)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        self.fs.create_file_from_bytes(self.share_name, None, file_name, data, progress_callback=callback)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)

    @record
    def test_create_file_from_bytes_with_index(self):
        # Arrange
        file_name = self._get_file_reference()
        data = self.get_random_bytes(2048)
        index = 1024

        # Act
        self.fs.create_file_from_bytes(self.share_name, None, file_name, data, index)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[1024:])

    @record
    def test_create_file_from_bytes_with_index_and_count(self):
        # Arrange
        file_name = self._get_file_reference()
        data = self.get_random_bytes(2048)
        index = 512
        count = 1024

        # Act
        resp = self.fs.create_file_from_bytes(self.share_name, None, file_name, data, index, count)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[index:index + count])

    @record
    def test_create_file_from_bytes_chunked_upload(self):
        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)

        # Act
        self.fs.create_file_from_bytes(self.share_name, None, file_name, data)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)

    def test_create_file_from_bytes_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)

        # Act
        self.fs.create_file_from_bytes(self.share_name, None, file_name, data, max_connections=5)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)

    @record
    def test_create_file_from_bytes_chunked_upload_with_index_and_count(self):
        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        index = 512
        count = len(data) - 1024

        # Act
        self.fs.create_file_from_bytes(self.share_name, None, file_name, data, index, count)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[index:index + count])

    def test_create_file_from_bytes_chunked_upload_with_index_and_count_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        index = 512
        count = len(data) - 1024

        # Act
        self.fs.create_file_from_bytes(self.share_name, None, file_name, data, index, count, max_connections=5)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[index:index + count])

    @record
    def test_create_file_from_path_chunked_upload(self):
        # Arrange        
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        self.fs.create_file_from_path(self.share_name, None, file_name, INPUT_FILE_PATH)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)

    def test_create_file_from_path_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        resp = self.fs.create_file_from_path(self.share_name, None, file_name, INPUT_FILE_PATH, max_connections=5)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)

    @record
    def test_create_file_from_path_with_progress_chunked_upload(self):
        # Arrange        
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        self.fs.create_file_from_path(self.share_name, None, file_name, INPUT_FILE_PATH, 
                                      progress_callback=callback)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)
        self.assertEqual(progress, self._get_expected_upload_progress(len(data), False))

    @record
    def test_create_file_from_stream_chunked_upload(self):
        # Arrange
        
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        file_size = len(data)
        with open(INPUT_FILE_PATH, 'rb') as stream:
            self.fs.create_file_from_stream(self.share_name, None, file_name, stream, file_size)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])

    def test_create_file_from_stream_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange        
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        file_size = len(data)
        with open(INPUT_FILE_PATH, 'rb') as stream:
            self.fs.create_file_from_stream(self.share_name, None, file_name, stream, 
                                            file_size, max_connections=5)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])

    @record
    def test_create_file_from_stream_non_seekable_chunked_upload(self):
        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        file_size = len(data)
        with open(INPUT_FILE_PATH, 'rb') as stream:
            non_seekable_file = StorageFileTest.NonSeekableFile(stream)
            self.fs.create_file_from_stream(self.share_name, None, file_name, 
                                            non_seekable_file, file_size)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])

    def test_create_file_from_stream_non_seekable_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange        
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        file_size = len(data)
        with open(INPUT_FILE_PATH, 'rb') as stream:
            non_seekable_file = StorageFileTest.NonSeekableFile(stream)

            # Parallel uploads require that the file be seekable
            with self.assertRaises(AttributeError):
                self.fs.create_file_from_stream(self.share_name, None, file_name, 
                                                non_seekable_file, file_size, max_connections=5)

        # Assert

    @record
    def test_create_file_from_stream_with_progress_chunked_upload(self):
        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file_size = len(data)
        with open(INPUT_FILE_PATH, 'rb') as stream:
            self.fs.create_file_from_stream(self.share_name, None, file_name, stream, 
                                            file_size, progress_callback=callback)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])
        self.assertEqual(progress, self._get_expected_upload_progress(len(data), False))

    def test_create_file_from_stream_with_progress_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange      
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file_size = len(data)
        with open(INPUT_FILE_PATH, 'rb') as stream:
            self.fs.create_file_from_stream(self.share_name, None, file_name, stream, 
                                            file_size, progress_callback=callback, max_connections=5)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])
        self.assertEqual(progress, self._get_expected_upload_progress(len(data), False))

    @record
    def test_create_file_from_stream_chunked_upload_truncated(self):
        # Arrange       
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        file_size = len(data) - 512
        with open(INPUT_FILE_PATH, 'rb') as stream:
            self.fs.create_file_from_stream(self.share_name, None, file_name, stream, file_size)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])

    def test_create_file_from_stream_chunked_upload_truncated_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange        
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        file_size = len(data) - 512
        with open(INPUT_FILE_PATH, 'rb') as stream:
            self.fs.create_file_from_stream(self.share_name, None, file_name, stream, 
                                            file_size, max_connections=5)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])

    @record
    def test_create_file_from_stream_with_progress_chunked_upload_truncated(self):
        # Arrange       
        file_name = self._get_file_reference()
        data = self.get_random_bytes(self.fs._FILE_MAX_DATA_SIZE + 512)
        with open(INPUT_FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        file_size = len(data) - 5
        with open(INPUT_FILE_PATH, 'rb') as stream:
            self.fs.create_file_from_stream(self.share_name, None, file_name, stream, 
                                            file_size, progress_callback=callback)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data[:file_size])
        self.assertEqual(progress, self._get_expected_upload_progress(file_size, False))


    @record
    def test_create_file_from_text(self):
        # Arrange
        file_name = self._get_file_reference()
        text = u'hello 啊齄丂狛狜 world'
        data = text.encode('utf-8')

        # Act
        self.fs.create_file_from_text(self.share_name, None, file_name, text)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)

    @record
    def test_create_file_from_text_with_encoding(self):
        # Arrange
        file_name = self._get_file_reference()
        text = u'hello 啊齄丂狛狜 world'
        data = text.encode('utf-16')

        # Act
        self.fs.create_file_from_text(self.share_name, None, file_name, text, 'utf-16')

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, data)

    @record
    def test_create_file_from_text_chunked_upload(self):
        # Arrange
        file_name = self._get_file_reference()
        data = self.get_random_text_data(self.fs._FILE_MAX_DATA_SIZE + 512)
        encoded_data = data.encode('utf-8')

        # Act
        self.fs.create_file_from_text(self.share_name, None, file_name, data)

        # Assert
        self.assertFileEqual(self.share_name, None, file_name, encoded_data)


    #--Test cases for sas & acl ------------------------------------------------
    @record
    def test_sas_access_file(self):
        # SAS URL is calculated from storage key, so this test runs live only
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        file_name = self._create_file()
        
        token = self.fs.generate_file_shared_access_signature(
            self.share_name,
            None,
            file_name,
            permission=FilePermissions.READ,
            expiry=datetime.utcnow() + timedelta(hours=1),
        )

        # Act
        service = FileService(
            self.settings.STORAGE_ACCOUNT_NAME,
            sas_token=token,
            request_session=requests.Session(),
        )
        self._set_service_options(service, self.settings)
        result = service.get_file_to_bytes(self.share_name, None, file_name)

        # Assert
        self.assertEqual(self.short_byte_data, result.content)

    @record
    def test_sas_signed_identifier(self):
        # SAS URL is calculated from storage key, so this test runs live only
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        file_name = self._create_file()

        access_policy = AccessPolicy()
        access_policy.start = '2011-10-11'
        access_policy.expiry = '2018-10-12'
        access_policy.permission = FilePermissions.READ
        identifiers = {'testid': access_policy}

        resp = self.fs.set_share_acl(self.share_name, identifiers)

        token = self.fs.generate_file_shared_access_signature(
            self.share_name,
            None,
            file_name,
            id='testid'
            )

        # Act
        service = FileService(
            self.settings.STORAGE_ACCOUNT_NAME,
            sas_token=token,
            request_session=requests.Session(),
        )
        self._set_service_options(service, self.settings)
        result = service.get_file_to_bytes(self.share_name, None, file_name)

        # Assert
        self.assertEqual(self.short_byte_data, result.content)


    @record
    def test_account_sas(self):
        # SAS URL is calculated from storage key, so this test runs live only
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        file_name = self._create_file()

        token = self.fs.generate_account_shared_access_signature(
            ResourceTypes.OBJECT,
            AccountPermissions.READ,
            datetime.utcnow() + timedelta(hours=1),
        )

        # Act
        url = self.fs.make_file_url(
            self.share_name,
            None,
            file_name,
            sas_token=token,
        )
        response = requests.get(url)

        # Assert
        self.assertTrue(response.ok)
        self.assertEqual(self.short_byte_data, response.content)

    @record
    def test_shared_read_access_file(self):
        # SAS URL is calculated from storage key, so this test runs live only
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        file_name = self._create_file()

        token = self.fs.generate_file_shared_access_signature(
            self.share_name,
            None,
            file_name,
            permission=FilePermissions.READ,
            expiry=datetime.utcnow() + timedelta(hours=1),
        )

        # Act
        url = self.fs.make_file_url(
            self.share_name,
            None,
            file_name,
            sas_token=token,
        )
        response = requests.get(url)

        # Assert
        self.assertTrue(response.ok)
        self.assertEqual(self.short_byte_data, response.content)

    @record
    def test_shared_read_access_file_with_content_query_params(self):
        # SAS URL is calculated from storage key, so this test runs live only
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        file_name = self._create_file()

        token = self.fs.generate_file_shared_access_signature(
            self.share_name,
            None,
            file_name,
            permission=FilePermissions.READ,
            expiry=datetime.utcnow() + timedelta(hours=1),
            cache_control='no-cache',
            content_disposition='inline',
            content_encoding='utf-8',
            content_language='fr',
            content_type='text',
        )
        url = self.fs.make_file_url(
            self.share_name,
            None,
            file_name,
            sas_token=token,
        )

        # Act
        response = requests.get(url)

        # Assert
        self.assertEqual(self.short_byte_data, response.content)
        self.assertEqual(response.headers['cache-control'], 'no-cache')
        self.assertEqual(response.headers['content-disposition'], 'inline')
        self.assertEqual(response.headers['content-encoding'], 'utf-8')
        self.assertEqual(response.headers['content-language'], 'fr')
        self.assertEqual(response.headers['content-type'], 'text')

    @record
    def test_shared_write_access_file(self):
        # SAS URL is calculated from storage key, so this test runs live only
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        updated_data = b'updated file data'
        file_name = self._create_file()

        token = self.fs.generate_file_shared_access_signature(
            self.share_name,
            None,
            file_name,
            permission=FilePermissions.WRITE,
            expiry=datetime.utcnow() + timedelta(hours=1),
        )
        url = self.fs.make_file_url(
            self.share_name,
            None,
            file_name,
            sas_token=token,
        )

        # Act
        headers={'x-ms-range': 'bytes=0-16', 'x-ms-write': 'update'} 
        response = requests.put(url + '&comp=range', headers=headers, data=updated_data)

        # Assert
        self.assertTrue(response.ok)
        file = self.fs.get_file_to_bytes(self.share_name, None, file_name)
        self.assertEqual(updated_data, file.content[:len(updated_data)])

    @record
    def test_shared_delete_access_file(self):
        # SAS URL is calculated from storage key, so this test runs live only
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        file_name = self._create_file()

        token = self.fs.generate_file_shared_access_signature(
            self.share_name,
            None,
            file_name,
            permission=FilePermissions.DELETE,
            expiry=datetime.utcnow() + timedelta(hours=1),
        )
        url = self.fs.make_file_url(
            self.share_name,
            None,
            file_name,
            sas_token=token,
        )

        # Act
        response = requests.delete(url)

        # Assert
        self.assertTrue(response.ok)
        with self.assertRaises(AzureMissingResourceHttpError):
            file = self.fs.get_file_to_bytes(self.share_name, None, file_name)


#------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()