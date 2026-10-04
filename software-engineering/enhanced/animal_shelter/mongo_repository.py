"""PyMongo adapter: driver errors stop here rather than becoming empty results."""
import logging
from typing import Any, Callable, TypeVar
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from .config import MongoConfig
from .errors import ConfigurationError, RepositoryError, ResourceClosedError
from .models import Document, CreateResult, ReadResult, UpdateResult, DeleteResult

logger = logging.getLogger(__name__)
T = TypeVar('T')

class MongoAnimalRepository:
    """Internal adapter; application callers should use the validating service."""
    def __init__(self, client: Any, collection: Any, timeout_ms: int) -> None:
        self._client = client
        self._collection = collection
        self._timeout_ms = timeout_ms
        self._closed = False

    @classmethod
    def connect(cls, config: MongoConfig, *, client_factory: Callable[..., Any] = MongoClient) -> 'MongoAnimalRepository':
        client = None
        try:
            client = client_factory(config.uri, serverSelectionTimeoutMS=config.timeout_ms,
                connectTimeoutMS=config.timeout_ms, socketTimeoutMS=config.timeout_ms,
                timeoutMS=config.timeout_ms, w=1)
            client.admin.command('ping')
            collection = client[config.database][config.collection]
            return cls(client, collection, config.timeout_ms)
        except (PyMongoError, ValueError, TypeError):
            if client is not None:
                client.close()
            logger.error('shelter_connection_failed', extra={'operation': 'connect', 'status': 'failure'})
            raise ConfigurationError('MongoDB connection failed. Check configuration and availability.') from None

    def _run(self, operation: str, action: Callable[[], T]) -> T:
        if self._closed:
            raise ResourceClosedError('MongoDB repository is closed.')
        try:
            return action()
        except PyMongoError:
            # Deliberately omit driver error text, query values and exception traces.
            logger.error('shelter_operation_failed', extra={'operation': operation, 'status': 'failure'})
            raise RepositoryError(f'MongoDB {operation} failed.') from None

    def create(self, data: Document) -> CreateResult:
        def action() -> CreateResult:
            result = self._collection.insert_one(dict(data))
            if not result.acknowledged:
                raise RepositoryError('MongoDB create was not acknowledged.')
            return CreateResult(str(result.inserted_id))
        return self._run('create', action)

    def read(self, filters: Document, limit: int) -> ReadResult:
        def action() -> ReadResult:
            cursor = self._collection.find(dict(filters)).limit(limit + 1).max_time_ms(self._timeout_ms)
            try:
                records = list(cursor)
            finally:
                cursor.close()
            return ReadResult(tuple(records[:limit]), len(records) > limit)
        return self._run('read', action)

    def update(self, record_id: ObjectId, changes: Document) -> UpdateResult:
        def action() -> UpdateResult:
            result = self._collection.update_one({'_id': record_id}, {'$set': dict(changes)})
            if not result.acknowledged:
                raise RepositoryError('MongoDB update was not acknowledged.')
            return UpdateResult(result.matched_count, result.modified_count)
        return self._run('update', action)

    def delete(self, record_id: ObjectId) -> DeleteResult:
        def action() -> DeleteResult:
            result = self._collection.delete_one({'_id': record_id})
            if not result.acknowledged:
                raise RepositoryError('MongoDB delete was not acknowledged.')
            return DeleteResult(result.deleted_count)
        return self._run('delete', action)

    def close(self) -> None:
        if not self._closed:
            self._client.close()
            self._closed = True
