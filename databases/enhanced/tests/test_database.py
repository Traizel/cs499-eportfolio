import unittest
from unittest.mock import MagicMock
from pymongo.errors import OperationFailure
from animal_shelter import search
from animal_shelter.errors import ValidationError, RepositoryError, ResourceClosedError
from animal_shelter.database_repository import DatabaseRepository, INDEX_NAME, INDEX_KEYS
from animal_shelter.database_service import DatabaseService

class PolicyTests(unittest.TestCase):
    def test_injection_rejected(self):
        for value in ({'$where': 'evil'}, {'breed': {'$ne': ''}}, {'breed.x': 'x'},
                      {'age_upon_outcome_in_weeks': True}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                search.specification(value)

    def test_invalid_options(self):
        for kw in ({'page': True}, {'page': 0}, {'page_size': 0}, {'page_size': 101},
                   {'page': 100002}, {'direction': True}, {'direction': 0},
                   {'sort_by': '$where'}, {'fields': 'breed'}, {'fields': []},
                   {'fields': ['$secret']}, {'category': 'unknown'},
                   {'min_age': float('nan')}, {'max_age': float('inf')},
                   {'min_age': True}, {'min_age': 50, 'max_age': 20}):
            with self.subTest(kw=kw), self.assertRaises(ValidationError):
                search.specification({}, **kw)

    def test_copy_sort_projection_and_offset(self):
        filters = {'breed': 'Labrador Retriever Mix'}
        spec = search.specification(filters, fields=['breed'], sort_by='breed', page=3, page_size=2)
        filters['breed'] = 'changed'
        self.assertEqual(spec.query['breed'], 'Labrador Retriever Mix')
        self.assertEqual(spec.sort, (('breed', 1), ('_id', 1)))
        self.assertEqual(spec.projection, {'breed': 1, '_id': 0})
        self.assertEqual(spec.offset, 4)

    def test_rescue_and_user_constraints_intersect(self):
        spec = search.specification({'animal_type': 'Cat'}, category='water', min_age=30)
        self.assertEqual(len(spec.query['$and']), 3)
        self.assertEqual(spec.query['$and'][0]['animal_type'], 'Cat')
        self.assertEqual(spec.query['$and'][2]['animal_type'], 'Dog')

    def test_summary_has_match_group_sort_limit(self):
        pipeline = search.summary_pipeline({}, category='water', limit=4)
        self.assertEqual([next(iter(x)) for x in pipeline], ['$match', '$group', '$sort', '$limit'])
        self.assertEqual(pipeline[1]['$group']['_id']['category'], {'$literal': 'water'})
        self.assertEqual(pipeline[-1], {'$limit': 4})
        with self.assertRaises(ValidationError):
            search.summary_pipeline({}, limit=True)

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.collection = MagicMock()
        self.collection.name = 'animals'
        self.repo = DatabaseRepository(self.client, self.collection, 1000)
        self.service = DatabaseService(self.repo)
        self.addCleanup(self.service.close)

    def cursor(self, records):
        cursor = MagicMock()
        for name in ('sort', 'skip', 'limit', 'max_time_ms'):
            getattr(cursor, name).return_value = cursor
        cursor.__iter__.return_value = iter(records)
        self.collection.find.return_value = cursor
        return cursor

    def test_search_bounds_and_next_page(self):
        cursor = self.cursor([{'name': 'a'}, {'name': 'b'}, {'name': 'c'}])
        result = self.service.search(page=2, page_size=2, sort_by='name', fields=['name'])
        self.assertEqual(result.records, ({'name': 'a'}, {'name': 'b'}))
        self.assertTrue(result.has_next)
        cursor.skip.assert_called_once_with(2)
        cursor.limit.assert_called_once_with(3)
        cursor.sort.assert_called_once_with([('name', 1), ('_id', 1)])
        cursor.close.assert_called_once()

    def test_empty_and_last_page(self):
        for values in ([], [{'name': 'a'}, {'name': 'b'}]):
            self.cursor(values)
            result = self.service.search(page_size=2)
            self.assertFalse(result.has_next)
            self.assertEqual(len(result.records), len(values))

    def test_failure_closes_cursor_and_hides_driver_details(self):
        cursor = self.cursor([])
        cursor.__iter__.side_effect = OperationFailure('PASSWORD_SENTINEL')
        with self.assertLogs('animal_shelter.mongo_repository', level='ERROR'):
            with self.assertRaises(RepositoryError) as e:
                self.service.search()
        self.assertNotIn('PASSWORD_SENTINEL', str(e.exception))
        cursor.close.assert_called_once()

    def test_invalid_input_never_calls_database(self):
        with self.assertRaises(ValidationError):
            self.service.search({'$where': 'evil'})
        self.collection.find.assert_not_called()

    def test_summary_closes_cursor_and_sets_timeout(self):
        cursor = MagicMock()
        cursor.__iter__.return_value = iter([{'_id': {'breed': 'X'}, 'count': 2}])
        self.collection.aggregate.return_value = cursor
        self.assertEqual(self.service.rescue_summary()[0]['count'], 2)
        self.assertEqual(self.collection.aggregate.call_args.kwargs, {'maxTimeMS': 1000, 'allowDiskUse': False})
        cursor.close.assert_called_once()

    def test_summary_failure_is_controlled(self):
        cursor = MagicMock()
        cursor.__iter__.side_effect = OperationFailure('SECRET')
        self.collection.aggregate.return_value = cursor
        with self.assertLogs('animal_shelter.mongo_repository', level='ERROR'):
            with self.assertRaises(RepositoryError):
                self.service.rescue_summary()
        cursor.close.assert_called_once()

    def test_index_creation_and_inventory(self):
        self.repo.ensure_indexes()
        self.collection.create_index.assert_called_once_with(INDEX_KEYS, name=INDEX_NAME)
        cursor = MagicMock()
        cursor.__iter__.return_value = iter([{'name': '_id_'}])
        self.collection.list_indexes.return_value = cursor
        self.assertEqual(self.repo.list_indexes(), [{'name': '_id_'}])
        cursor.close.assert_called_once()

    def test_explain_uses_same_options_and_restricted_hint(self):
        spec = search.specification({}, page=2, page_size=2, fields=['breed'])
        self.repo.explain(spec, hint='natural')
        args, kwargs = self.collection.database.command.call_args
        self.assertEqual(args[0], 'explain')
        self.assertEqual(args[1]['hint'], {'$natural': 1})
        self.assertEqual(args[1]['skip'], 2)
        self.assertEqual(args[1]['limit'], 3)
        self.assertEqual(kwargs['verbosity'], 'executionStats')
        with self.assertRaises(ValueError):
            self.repo.explain(spec, hint='$evil')

    def test_closed_service_prevents_database_search(self):
        self.service.close()
        with self.assertRaises(ResourceClosedError):
            self.service.search()
        self.collection.find.assert_not_called()

if __name__ == '__main__':
    unittest.main()
