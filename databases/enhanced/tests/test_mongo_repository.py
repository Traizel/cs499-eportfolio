"""Adapter contract tests use real PyMongo result/error types with mocked I/O.

These tests do not claim to validate a live MongoDB server or credentials.
"""
import traceback
import unittest
from unittest.mock import MagicMock, Mock
from bson import ObjectId
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError
from pymongo.results import InsertOneResult, UpdateResult as MongoUpdateResult, DeleteResult as MongoDeleteResult
from animal_shelter.config import MongoConfig
from animal_shelter.errors import ConfigurationError, RepositoryError, ResourceClosedError
from animal_shelter.models import UpdateResult, DeleteResult
from animal_shelter.mongo_repository import MongoAnimalRepository

class MongoAdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.collection = MagicMock()
        self.repo = MongoAnimalRepository(self.client, self.collection, 1000)
        self.addCleanup(self.repo.close)
        self.identity = ObjectId()

    def test_create_copies_input_and_returns_inserted_id(self):
        data = {'animal_id': 'A', 'animal_type': 'Dog'}
        def insert(copy):
            copy['_id'] = self.identity
            return InsertOneResult(self.identity, True)
        self.collection.insert_one.side_effect = insert
        self.assertEqual(self.repo.create(data).inserted_id, str(self.identity))
        self.assertNotIn('_id', data)

    def test_update_uses_id_set_and_preserves_matched_vs_modified(self):
        self.collection.update_one.return_value = MongoUpdateResult({'n': 1, 'nModified': 0}, True)
        self.assertEqual(self.repo.update(self.identity, {'name': 'Same'}), UpdateResult(1, 0))
        self.collection.update_one.assert_called_once_with({'_id': self.identity}, {'$set': {'name': 'Same'}})
        self.collection.update_many.assert_not_called()

    def test_delete_uses_unique_id_and_one_operation(self):
        self.collection.delete_one.return_value = MongoDeleteResult({'n': 1}, True)
        self.assertEqual(self.repo.delete(self.identity), DeleteResult(1))
        self.collection.delete_one.assert_called_once_with({'_id': self.identity})
        self.collection.delete_many.assert_not_called()

    def _cursor(self, documents):
        cursor = MagicMock()
        self.collection.find.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.max_time_ms.return_value = cursor
        cursor.__iter__.return_value = iter(documents)
        return cursor

    def test_read_caps_results_and_closes_cursor(self):
        cursor = self._cursor([{'name': 'a'}, {'name': 'b'}, {'name': 'c'}])
        result = self.repo.read({}, 2)
        self.assertEqual(len(result.records), 2)
        self.assertTrue(result.truncated)
        cursor.limit.assert_called_once_with(3)
        cursor.max_time_ms.assert_called_once_with(1000)
        cursor.close.assert_called_once()

    def test_cursor_failure_closes_cursor_and_raises_safe_error(self):
        cursor = self._cursor([])
        cursor.__iter__.side_effect = OperationFailure('SECRET_DRIVER_TEXT')
        with self.assertLogs('animal_shelter.mongo_repository', level='ERROR') as logs:
            with self.assertRaises(RepositoryError) as raised:
                self.repo.read({}, 2)
        cursor.close.assert_called_once()
        self.assertNotIn('SECRET_DRIVER_TEXT', str(raised.exception))
        self.assertNotIn('SECRET_DRIVER_TEXT', str(logs.records[0].__dict__))

    def test_all_driver_operation_failures_are_translated(self):
        calls = [('create', 'insert_one', ({'animal_id': 'A'},)),
                 ('read', 'find', ({}, 2)), ('update', 'update_one', (self.identity, {'name': 'X'})),
                 ('delete', 'delete_one', (self.identity,))]
        for operation, method, args in calls:
            with self.subTest(operation=operation):
                getattr(self.collection, method).side_effect = OperationFailure('PASSWORD_SENTINEL')
                with self.assertLogs('animal_shelter.mongo_repository', level='ERROR') as logs:
                    try:
                        getattr(self.repo, operation)(*args)
                    except RepositoryError as error:
                        formatted = ''.join(traceback.format_exception(error))
                        self.assertNotIn('PASSWORD_SENTINEL', formatted)
                    else:
                        self.fail('Expected RepositoryError')
                self.assertEqual(logs.records[0].operation, operation)
                self.assertNotIn('PASSWORD_SENTINEL', str(logs.records[0].__dict__))

    def test_unacknowledged_writes_are_not_reported_as_success(self):
        self.collection.insert_one.return_value = InsertOneResult(self.identity, False)
        self.collection.update_one.return_value = MongoUpdateResult({}, False)
        self.collection.delete_one.return_value = MongoDeleteResult({}, False)
        for action in (lambda: self.repo.create({}), lambda: self.repo.update(self.identity, {}), lambda: self.repo.delete(self.identity)):
            with self.assertRaises(RepositoryError):
                action()

    def test_connect_pings_and_sets_finite_timeouts_and_acknowledgement(self):
        factory = Mock(return_value=self.client)
        config = MongoConfig('mongodb://localhost/', timeout_ms=1000)
        repo = MongoAnimalRepository.connect(config, client_factory=factory)
        self.addCleanup(repo.close)
        self.client.admin.command.assert_called_once_with('ping')
        self.assertEqual(factory.call_args.kwargs, {'serverSelectionTimeoutMS': 1000,
            'connectTimeoutMS': 1000, 'socketTimeoutMS': 1000, 'timeoutMS': 1000, 'w': 1})

    def test_connect_failure_closes_partial_client_and_hides_secrets(self):
        self.client.admin.command.side_effect = ServerSelectionTimeoutError('URI_PASSWORD_SENTINEL')
        with self.assertLogs('animal_shelter.mongo_repository', level='ERROR') as logs:
            with self.assertRaises(ConfigurationError) as raised:
                MongoAnimalRepository.connect(MongoConfig('mongodb://localhost/'), client_factory=Mock(return_value=self.client))
        self.client.close.assert_called_once()
        self.assertNotIn('URI_PASSWORD_SENTINEL', str(raised.exception))
        self.assertNotIn('URI_PASSWORD_SENTINEL', str(logs.records[0].__dict__))

    def test_malformed_uri_factory_error_becomes_configuration_error(self):
        with self.assertLogs('animal_shelter.mongo_repository', level='ERROR'):
            with self.assertRaises(ConfigurationError):
                MongoAnimalRepository.connect(MongoConfig('mongodb://'), client_factory=Mock(side_effect=ValueError('bad URI')))

    def test_close_is_idempotent_and_blocks_later_operations(self):
        self.repo.close()
        self.repo.close()
        self.client.close.assert_called_once()
        with self.assertRaises(ResourceClosedError):
            self.repo.read({}, 1)
