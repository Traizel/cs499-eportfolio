"""Trusted MongoDB adapter with bounded queries, aggregation and index evaluation."""
from dataclasses import dataclass
from .mongo_repository import MongoAnimalRepository

INDEX_NAME = 'rescue_filter_v1'
INDEX_KEYS = [('animal_type', 1), ('breed', 1), ('sex_upon_outcome', 1),
              ('age_upon_outcome_in_weeks', 1), ('_id', 1)]

@dataclass(frozen=True)
class SearchResult:
    records: tuple
    page: int
    page_size: int
    has_next: bool

class DatabaseRepository(MongoAnimalRepository):
    def ensure_indexes(self):
        """Administrative setup only; idempotent creation does not drop existing indexes."""
        return self._run('ensure_indexes', lambda: self._collection.create_index(
            INDEX_KEYS, name=INDEX_NAME))

    def list_indexes(self):
        def action():
            cursor = self._collection.list_indexes()
            try:
                return list(cursor)
            finally:
                cursor.close()
        return self._run('list_indexes', action)

    def search(self, spec):
        def action():
            cursor = self._collection.find(spec.query, spec.projection)
            try:
                cursor.sort(list(spec.sort)).skip(spec.offset).limit(spec.page_size + 1).max_time_ms(self._timeout_ms)
                records = list(cursor)
                return SearchResult(tuple(records[:spec.page_size]), spec.page,
                                    spec.page_size, len(records) > spec.page_size)
            finally:
                cursor.close()
        return self._run('search', action)

    def rescue_summary(self, pipeline):
        def action():
            cursor = self._collection.aggregate(pipeline, maxTimeMS=self._timeout_ms, allowDiskUse=False)
            try:
                return tuple(cursor)
            finally:
                cursor.close()
        return self._run('rescue_summary', action)

    def explain(self, spec, *, hint=None):
        """Diagnostic API, accepts only a natural scan or this package's index hint."""
        if hint not in (None, 'natural', INDEX_NAME):
            raise ValueError('Unsupported diagnostic hint.')
        command = {'find': self._collection.name, 'filter': spec.query,
                   'sort': dict(spec.sort), 'skip': spec.offset,
                   'limit': spec.page_size + 1}
        if spec.projection is not None:
            command['projection'] = spec.projection
        if hint is not None:
            command['hint'] = {'$natural': 1} if hint == 'natural' else hint
        return self._run('explain', lambda: self._collection.database.command(
            'explain', command, verbosity='executionStats', maxTimeMS=self._timeout_ms))
