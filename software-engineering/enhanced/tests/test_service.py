"""Behavior tests exercise real validation with an injected offline repository."""
import unittest
from unittest.mock import Mock
from bson import ObjectId
from animal_shelter import AnimalService, ValidationError, ResourceClosedError, RepositoryError
from animal_shelter.memory_repository import MemoryAnimalRepository
from animal_shelter.models import UpdateResult, DeleteResult

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = AnimalService(MemoryAnimalRepository())
        self.addCleanup(self.service.close)
        self.data = {'animal_id': 'TEST1', 'animal_type': 'Dog', 'name': 'Scout'}

    def test_full_crud_workflow_preserves_other_records(self):
        one = self.service.create(self.data)
        two = self.service.create({**self.data, 'animal_id': 'TEST2'})
        self.assertEqual(self.service.update(one.inserted_id, {'name': 'New'}), UpdateResult(1, 1))
        self.assertEqual(self.service.read({'_id': one.inserted_id}).records[0]['name'], 'New')
        self.assertEqual(self.service.read({'_id': two.inserted_id}).records[0]['name'], 'Scout')
        self.assertEqual(self.service.delete(one.inserted_id), DeleteResult(1))
        self.assertEqual(len(self.service.read({}).records), 1)

    def test_unchanged_update_is_distinct_from_missing_record(self):
        created = self.service.create(self.data)
        self.assertEqual(self.service.update(created.inserted_id, {'name': 'Scout'}), UpdateResult(1, 0))
        self.assertEqual(self.service.update(ObjectId(), {'name': 'Scout'}), UpdateResult(0, 0))

    def test_empty_result_is_success(self):
        result = self.service.read({'animal_type': 'Cat'})
        self.assertEqual(result.records, ())
        self.assertFalse(result.truncated)
        self.assertEqual(self.service.delete(ObjectId()), DeleteResult(0))

    def test_limit_reports_truncation_without_hiding_it(self):
        for _ in range(3):
            self.service.create(self.data)
        result = self.service.read({}, limit=2)
        self.assertEqual(len(result.records), 2)
        self.assertTrue(result.truncated)
        self.assertFalse(self.service.read({}, limit=3).truncated)

    def test_create_and_read_do_not_expose_mutable_stored_data(self):
        created = self.service.create(self.data)
        self.assertNotIn('_id', self.data)
        self.data['name'] = 'Changed outside'
        records = self.service.read({}).records
        records[0]['name'] = 'Changed result'
        self.assertEqual(self.service.read({'_id': created.inserted_id}).records[0]['name'], 'Scout')

    def test_reject_missing_required_fields(self):
        for data in ({}, None, [], {'animal_id': 'A'}, {'animal_type': 'Dog'}, {'animal_id': ' ', 'animal_type': 'Dog'}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                self.service.create(data)

    def test_operator_and_unknown_field_inputs_never_reach_repository(self):
        repo = Mock()
        service = AnimalService(repo)
        for data in ({'$where': 'code'}, {'name': {'$ne': None}}, {'name.x': 'bad'}, {'unknown': 'bad'}, {1: 'bad'}, {'name': ['bad']}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                service.read(data)
        repo.read.assert_not_called()

    def test_invalid_measurements_are_rejected(self):
        for value in (True, '2', float('nan'), float('inf'), -1, 10001, 10**1000):
            with self.subTest(value=str(value)[:30]), self.assertRaises(ValidationError):
                self.service.create({**self.data, 'age_upon_outcome_in_weeks': value})
        for key,value in [('location_lat', 91), ('location_long', -181)]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.service.create({**self.data, key: value})

    def test_measurement_boundaries_and_optional_empty_name(self):
        created = self.service.create({**self.data, 'name': '', 'age_upon_outcome_in_weeks': 0,
                                       'location_lat': -90, 'location_long': 180})
        self.assertTrue(created.inserted_id)

    def test_reject_oversized_or_nul_text(self):
        for name in ('x' * 257, 'a\x00b'):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.service.create({**self.data, 'name': name})

    def test_invalid_limits_never_reach_repository(self):
        for value in (0, -1, True, 1001, '10', 1.5):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.service.read({}, limit=value)

    def test_mutations_reject_broad_filters_and_invalid_ids(self):
        for identity in ({}, {'animal_type': 'Dog'}, 'invalid', None):
            with self.subTest(identity=identity), self.assertRaises(ValidationError):
                self.service.update(identity, {'name': 'bad'})
            with self.subTest(identity=identity), self.assertRaises(ValidationError):
                self.service.delete(identity)

    def test_update_rejects_empty_changes_operators_and_id_mutation(self):
        identity = ObjectId()
        for changes in ({}, {'_id': ObjectId()}, {'$set': {'name': 'bad'}}, {'animal_type': ''}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.service.update(identity, changes)

    def test_context_manager_closes_repository_after_exception(self):
        repo = Mock()
        service = AnimalService(repo)
        with self.assertRaisesRegex(RuntimeError, 'body failed'):
            with service:
                raise RuntimeError('body failed')
        service.close()
        repo.close.assert_called_once()
        with self.assertRaises(ResourceClosedError):
            service.read({})

    def test_repository_failure_is_not_an_empty_result(self):
        repo = Mock()
        repo.read.side_effect = RepositoryError('Database unavailable')
        with self.assertRaises(RepositoryError):
            AnimalService(repo).read({})

    def test_logs_contain_metadata_but_not_record_values(self):
        with self.assertLogs('animal_shelter.service', level='INFO') as captured:
            self.service.create({**self.data, 'name': 'PRIVATE_SENTINEL'})
        record = captured.records[0]
        self.assertEqual(record.operation, 'create')
        self.assertEqual(record.status, 'success')
        self.assertNotIn('PRIVATE_SENTINEL', str(record.__dict__))
