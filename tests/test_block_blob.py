# coding: utf-8

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
import os
import unittest

from azure.common import AzureHttpError
from azure.storage.blob import (
    BlobBlock,
    BlobBlockList,
    BlockBlobService,
    ContentSettings,
)
from tests.testcase import (
    StorageTestCase,
    TestMode,
    record,
)

#------------------------------------------------------------------------------
TEST_BLOB_PREFIX = 'blob'
FILE_PATH = 'blob_input.temp.dat'
#------------------------------------------------------------------------------

class StorageBlockBlobTest(StorageTestCase):

    def setUp(self):
        super(StorageBlockBlobTest, self).setUp()

        self.bs = self._create_storage_service(BlockBlobService, self.settings)
        self.container_name = self.get_resource_name('utcontainer')

        if not self.is_playback():
            self.bs.create_container(self.container_name)

        # test chunking functionality by reducing the threshold
        # for chunking and the size of each chunk, otherwise
        # the tests would take too long to execute
        self.bs._BLOB_MAX_DATA_SIZE = 64 * 1024
        self.bs._BLOB_MAX_CHUNK_DATA_SIZE = 4 * 1024

    def tearDown(self):
        if not self.is_playback():
            try:
                self.bs.delete_container(self.container_name)
            except:
                pass

        if os.path.isfile(FILE_PATH):
            try:
                os.remove(FILE_PATH)
            except:
                pass

        return super(StorageBlockBlobTest, self).tearDown()

    #--Helpers-----------------------------------------------------------------
    def _get_blob_reference(self):
        return self.get_resource_name(TEST_BLOB_PREFIX)

    def _create_blob(self):
        blob_name = self._get_blob_reference()
        self.bs.create_blob_from_bytes(self.container_name, blob_name, b'')
        return blob_name

    def assertBlobEqual(self, container_name, blob_name, expected_data):
        actual_data = self.bs.get_blob_to_bytes(container_name, blob_name)
        self.assertEqual(actual_data.content, expected_data)

    def _get_expected_progress(self, blob_size, unknown_size=False):
        result = []
        index = 0
        total = None if unknown_size else blob_size
        while (index < blob_size):
            result.append((index, total))
            index += self.bs._BLOB_MAX_CHUNK_DATA_SIZE
        result.append((blob_size, total))
        return result

    class NonSeekableFile(object):
        def __init__(self, wrapped_file):
            self.wrapped_file = wrapped_file

        def write(self, data):
            self.wrapped_file.write(data)

        def read(self, count):
            return self.wrapped_file.read(count)

    #--Test cases for block blobs --------------------------------------------

    @record
    def test_put_block(self):
        # Arrange
        blob_name = self._create_blob()

        # Act
        for i in range(5):
            resp = self.bs.put_block(self.container_name,
                                     blob_name,
                                     'block {0}'.format(i).encode('utf-8'),
                                     i)
            self.assertIsNone(resp)

        # Assert

    @record
    def test_put_block_unicode(self):
        # Arrange
        blob_name = self._create_blob()

        # Act
        with self.assertRaises(TypeError):
            resp = self.bs.put_block(self.container_name, blob_name, u'啊齄丂狛狜', '1')

        # Assert

    @record
    def test_put_block_list(self):
        # Arrange
        blob_name = self._get_blob_reference()
        self.bs.put_block(self.container_name, blob_name, b'AAA', '1')
        self.bs.put_block(self.container_name, blob_name, b'BBB', '2')
        self.bs.put_block(self.container_name, blob_name, b'CCC', '3')

        # Act
        block_list = [BlobBlock(id='1'), BlobBlock(id='2'), BlobBlock(id='3')]
        self.bs.put_block_list(self.container_name, blob_name, block_list)

        # Assert
        blob = self.bs.get_blob_to_bytes(self.container_name, blob_name)
        self.assertEqual(blob.content, b'AAABBBCCC')

    @record
    def test_put_block_list_invalid_block_id(self):
        # Arrange
        blob_name = self._get_blob_reference()
        self.bs.put_block(self.container_name, blob_name, b'AAA', '1')
        self.bs.put_block(self.container_name, blob_name, b'BBB', '2')
        self.bs.put_block(self.container_name, blob_name, b'CCC', '3')

        # Act
        try:
            block_list = [ BlobBlock(id='1'), BlobBlock(id='2'), BlobBlock(id='4')]
            self.bs.put_block_list(self.container_name, blob_name, block_list)
            self.fail()
        except AzureHttpError as e:
            self.assertGreaterEqual(str(e).find('specified block list is invalid'), 0)

        # Assert

    @record
    def test_get_block_list_no_blocks(self):
        # Arrange
        blob_name = self._create_blob()

        # Act
        block_list = self.bs.get_block_list(self.container_name, blob_name, None, 'all')

        # Assert
        self.assertIsNotNone(block_list)
        self.assertIsInstance(block_list, BlobBlockList)
        self.assertEqual(len(block_list.uncommitted_blocks), 0)
        self.assertEqual(len(block_list.committed_blocks), 0)

    @record
    def test_get_block_list_uncommitted_blocks(self):
        # Arrange
        blob_name = self._get_blob_reference()
        self.bs.put_block(self.container_name, blob_name, b'AAA', '1')
        self.bs.put_block(self.container_name, blob_name, b'BBB', '2')
        self.bs.put_block(self.container_name, blob_name, b'CCC', '3')

        # Act
        block_list = self.bs.get_block_list(self.container_name, blob_name, None, 'all')

        # Assert
        self.assertIsNotNone(block_list)
        self.assertIsInstance(block_list, BlobBlockList)
        self.assertEqual(len(block_list.uncommitted_blocks), 3)
        self.assertEqual(len(block_list.committed_blocks), 0)
        self.assertEqual(block_list.uncommitted_blocks[0].id, '1')
        self.assertEqual(block_list.uncommitted_blocks[0].size, 3)
        self.assertEqual(block_list.uncommitted_blocks[1].id, '2')
        self.assertEqual(block_list.uncommitted_blocks[1].size, 3)
        self.assertEqual(block_list.uncommitted_blocks[2].id, '3')
        self.assertEqual(block_list.uncommitted_blocks[2].size, 3)

    @record
    def test_get_block_list_committed_blocks(self):
        # Arrange
        blob_name = self._get_blob_reference()
        self.bs.put_block(self.container_name, blob_name, b'AAA', '1')
        self.bs.put_block(self.container_name, blob_name, b'BBB', '2')
        self.bs.put_block(self.container_name, blob_name, b'CCC', '3')

        block_list = [BlobBlock(id='1'), BlobBlock(id='2'), BlobBlock(id='3')]
        self.bs.put_block_list(self.container_name, blob_name, block_list)

        # Act
        block_list = self.bs.get_block_list(self.container_name, blob_name, None, 'all')

        # Assert
        self.assertIsNotNone(block_list)
        self.assertIsInstance(block_list, BlobBlockList)
        self.assertEqual(len(block_list.uncommitted_blocks), 0)
        self.assertEqual(len(block_list.committed_blocks), 3)
        self.assertEqual(block_list.committed_blocks[0].id, '1')
        self.assertEqual(block_list.committed_blocks[0].size, 3)
        self.assertEqual(block_list.committed_blocks[1].id, '2')
        self.assertEqual(block_list.committed_blocks[1].size, 3)
        self.assertEqual(block_list.committed_blocks[2].id, '3')
        self.assertEqual(block_list.committed_blocks[2].size, 3)

    @record
    def test_create_blob_from_bytes_single_put(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = b'hello world'

        # Act
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    @record
    def test_create_from_bytes_blob_unicode(self):
        # Arrange
        blob_name = self._get_blob_reference()

        # Act
        data = u'hello world'
        with self.assertRaises(TypeError):
            resp = self.bs.create_blob_from_bytes(self.container_name, blob_name, data)

        # Assert

    @record
    def test_create_from_bytes_blob_with_lease_id(self):
        # Arrange
        blob_name = self._create_blob()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        lease_id = self.bs.acquire_blob_lease(self.container_name, blob_name)

        # Act
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, lease_id=lease_id)

        # Assert
        blob = self.bs.get_blob_to_bytes(self.container_name, blob_name, lease_id=lease_id)
        self.assertEqual(blob.content, data)

    @record
    def test_create_blob_from_bytes_with_metadata(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        metadata = {'hello': 'world', 'number': '42'}

        # Act
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, metadata=metadata)

        # Assert
        md = self.bs.get_blob_metadata(self.container_name, blob_name)
        self.assertDictEqual(md, metadata)

    @record
    def test_create_blob_from_bytes_with_progress(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, progress_callback=callback)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        self.assertEqual(progress, self._get_expected_progress(len(data)))

    @record
    def test_create_blob_from_bytes_with_index(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)

        # Act
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, 3)

        # Assert
        self.assertEqual(data[3:], self.bs.get_blob_to_bytes(self.container_name, blob_name).content)

    @record
    def test_create_blob_from_bytes_with_index_and_count(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)

        # Act
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, 3, 5)

        # Assert
        self.assertEqual(data[3:8], self.bs.get_blob_to_bytes(self.container_name, blob_name).content)

    @record
    def test_create_blob_from_bytes_with_index_and_count_and_properties(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)

        # Act
        content_settings=ContentSettings(
                content_type='image/png',
                content_language='spanish')
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, 3, 5, content_settings=content_settings)

        # Assert
        self.assertEqual(data[3:8], self.bs.get_blob_to_bytes(self.container_name, blob_name).content)
        properties = self.bs.get_blob_properties(self.container_name, blob_name).properties
        self.assertEqual(properties.content_settings.content_type, content_settings.content_type)
        self.assertEqual(properties.content_settings.content_language, content_settings.content_language)

    def test_create_blob_from_bytes_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)

        # Act
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    @record
    def test_create_blob_from_bytes_parallel_with_properties(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return        
        
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)

        # Act
        content_settings=ContentSettings(
                content_type='image/png',
                content_language='spanish')
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, 
                                       content_settings=content_settings, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        properties = self.bs.get_blob_properties(self.container_name, blob_name).properties
        self.assertEqual(properties.content_settings.content_type, content_settings.content_type)
        self.assertEqual(properties.content_settings.content_language, content_settings.content_language)

    @record
    def test_create_blob_from_bytes_parallel_with_progress(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, 
                                       progress_callback=callback, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        self.assertEqual(progress, self._get_expected_progress(len(data)))

    @record
    def test_create_blob_from_bytes_parallel_with_index_and_count(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        index = 33
        blob_size = len(data) - 66

        # Act
        self.bs.create_blob_from_bytes(self.container_name, blob_name, data, 
                                       index, blob_size, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data[index:index + blob_size])

    @record
    def test_create_blob_from_path(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        self.bs.create_blob_from_path(self.container_name, blob_name, FILE_PATH)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    def test_create_blob_from_path_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        self.bs.create_blob_from_path(self.container_name, blob_name, FILE_PATH, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    @record
    def test_create_blob_from_path_with_progress_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        self.bs.create_blob_from_path(self.container_name, blob_name, FILE_PATH,
                                      progress_callback=callback, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        self.assertEqual(progress, self._get_expected_progress(len(data)))

    @record
    def test_create_blob_from_path_parallel_with_properties(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        content_settings=ContentSettings(
            content_type='image/png',
            content_language='spanish')
        self.bs.create_blob_from_path(self.container_name, blob_name, FILE_PATH, content_settings=content_settings)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        properties = self.bs.get_blob_properties(self.container_name, blob_name).properties
        self.assertEqual(properties.content_settings.content_type, content_settings.content_type)
        self.assertEqual(properties.content_settings.content_language, content_settings.content_language)

    @record
    def test_create_blob_from_stream_chunked_upload(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        with open(FILE_PATH, 'rb') as stream:
            self.bs.create_blob_from_stream(self.container_name, blob_name, stream)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    def test_create_blob_from_stream_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        with open(FILE_PATH, 'rb') as stream:
            self.bs.create_blob_from_stream(self.container_name, blob_name, stream, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    @record
    def test_create_blob_from_stream_non_seekable_chunked_upload_known_size(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        blob_size = len(data) - 66
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        with open(FILE_PATH, 'rb') as stream:
            non_seekable_file = StorageBlockBlobTest.NonSeekableFile(stream)
            self.bs.create_blob_from_stream(self.container_name, blob_name, non_seekable_file, count=blob_size)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data[:blob_size])

    @record
    def test_create_blob_from_stream_non_seekable_chunked_upload_unknown_size(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)


        # Act
        with open(FILE_PATH, 'rb') as stream:
            non_seekable_file = StorageBlockBlobTest.NonSeekableFile(stream)
            self.bs.create_blob_from_stream(self.container_name, blob_name, non_seekable_file)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    def test_create_blob_from_stream_non_seekable_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        with open(FILE_PATH, 'rb') as stream:
            non_seekable_file = StorageBlockBlobTest.NonSeekableFile(stream)

            # Parallel uploads require that the file be seekable
            with self.assertRaises(AttributeError):
                self.bs.create_blob_from_stream(self.container_name, blob_name, non_seekable_file, max_connections=5)

        # Assert

    @record
    def test_create_blob_from_stream_with_progress_chunked_upload(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        with open(FILE_PATH, 'rb') as stream:
            self.bs.create_blob_from_stream(self.container_name, blob_name, stream, progress_callback=callback)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        self.assertEqual(progress, self._get_expected_progress(len(data), unknown_size=True))

    def test_create_blob_from_stream_with_progress_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        with open(FILE_PATH, 'rb') as stream:
            self.bs.create_blob_from_stream(self.container_name, blob_name, stream, 
                                            progress_callback=callback, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        self.assertEqual(progress, self._get_expected_progress(len(data), unknown_size=True))

    @record
    def test_create_blob_from_stream_chunked_upload_with_count(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        blob_size = len(data) - 301
        with open(FILE_PATH, 'rb') as stream:
            resp = self.bs.create_blob_from_stream(self.container_name, blob_name, stream, blob_size)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data[:blob_size])

    def test_create_blob_from_stream_chunked_upload_with_count_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        blob_size = len(data) - 301
        with open(FILE_PATH, 'rb') as stream:
            self.bs.create_blob_from_stream(self.container_name, blob_name, stream, 
                                            blob_size, max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data[:blob_size])

    @record
    def test_create_blob_from_stream_chunked_upload_with_count_and_properties(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        content_settings=ContentSettings(
            content_type='image/png',
            content_language='spanish')
        blob_size = len(data) - 301
        with open(FILE_PATH, 'rb') as stream:
            self.bs.create_blob_from_stream(self.container_name, blob_name, stream, 
                                            blob_size, content_settings=content_settings)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data[:blob_size])
        properties = self.bs.get_blob_properties(self.container_name, blob_name).properties
        self.assertEqual(properties.content_settings.content_type, content_settings.content_type)
        self.assertEqual(properties.content_settings.content_language, content_settings.content_language)

    @record
    def test_create_blob_from_stream_chunked_upload_with_properties(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_bytes(self.bs._BLOB_MAX_DATA_SIZE + 1)
        with open(FILE_PATH, 'wb') as stream:
            stream.write(data)

        # Act
        content_settings=ContentSettings(
            content_type='image/png',
            content_language='spanish')
        with open(FILE_PATH, 'rb') as stream:
            self.bs.create_blob_from_stream(self.container_name, blob_name, stream, 
                                            content_settings=content_settings)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        properties = self.bs.get_blob_properties(self.container_name, blob_name).properties
        self.assertEqual(properties.content_settings.content_type, content_settings.content_type)
        self.assertEqual(properties.content_settings.content_language, content_settings.content_language)

    @record
    def test_create_blob_from_text(self):
        # Arrange
        blob_name = self._get_blob_reference()
        text = u'hello 啊齄丂狛狜 world'
        data = text.encode('utf-8')

        # Act
        self.bs.create_blob_from_text(self.container_name, blob_name, text)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    @record
    def test_create_blob_from_text_with_encoding(self):
        # Arrange
        blob_name = self._get_blob_reference()
        text = u'hello 啊齄丂狛狜 world'
        data = text.encode('utf-16')

        # Act
        self.bs.create_blob_from_text(self.container_name, blob_name, text, 'utf-16')

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)

    @record
    def test_create_blob_from_text_with_encoding_and_progress(self):
        # Arrange
        blob_name = self._get_blob_reference()
        text = u'hello 啊齄丂狛狜 world'
        data = text.encode('utf-16')

        # Act
        progress = []

        def callback(current, total):
            progress.append((current, total))

        self.bs.create_blob_from_text(self.container_name, blob_name, text, 'utf-16', 
                                      progress_callback=callback)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, data)
        self.assertEqual(progress, self._get_expected_progress(len(data)))

    @record
    def test_create_blob_from_text_chunked_upload(self):
        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_text_data(self.bs._BLOB_MAX_DATA_SIZE + 1)
        encoded_data = data.encode('utf-8')

        # Act
        self.bs.create_blob_from_text(self.container_name, blob_name, data)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, encoded_data)

    def test_create_blob_from_text_chunked_upload_parallel(self):
        # parallel tests introduce random order of requests, can only run live
        if TestMode.need_recordingfile(self.test_mode):
            return

        # Arrange
        blob_name = self._get_blob_reference()
        data = self.get_random_text_data(self.bs._BLOB_MAX_DATA_SIZE + 1)
        encoded_data = data.encode('utf-8')

        # Act
        self.bs.create_blob_from_text(self.container_name, blob_name, data, 
                                      max_connections=5)

        # Assert
        self.assertBlobEqual(self.container_name, blob_name, encoded_data)

#------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()