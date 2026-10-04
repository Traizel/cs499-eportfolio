"""Application API with validation, typed results and explicit resource ownership."""
import logging
from types import TracebackType
from typing import Type
from . import validation
from .errors import ResourceClosedError
from .models import CreateResult, ReadResult, UpdateResult, DeleteResult
from .repository import AnimalRepository

logger = logging.getLogger(__name__)

class AnimalService:
    """Own the injected repository; use one service per repository lifecycle."""
    def __init__(self, repository: AnimalRepository) -> None:
        self._repository = repository
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ResourceClosedError('Animal service is closed.')

    def create(self, data: object) -> CreateResult:
        self._ensure_open()
        result = self._repository.create(validation.document(data, mode='create'))
        logger.info('shelter_operation', extra={'operation': 'create', 'status': 'success'})
        return result

    def read(self, filters: object, *, limit: int = 100) -> ReadResult:
        self._ensure_open()
        query = validation.document(filters, mode='filter')
        count = validation.result_limit(limit)
        result = self._repository.read(query, count)
        logger.info('shelter_operation', extra={'operation': 'read', 'status': 'success',
                    'record_count': len(result.records), 'truncated': result.truncated})
        return result

    def update(self, record_id: object, changes: object) -> UpdateResult:
        """Update only the unique MongoDB _id, never an arbitrary bulk filter."""
        self._ensure_open()
        identity = validation.object_id(record_id)
        values = validation.document(changes, mode='update')
        result = self._repository.update(identity, values)
        logger.info('shelter_operation', extra={'operation': 'update', 'status': 'success',
                    'matched_count': result.matched_count, 'modified_count': result.modified_count})
        return result

    def delete(self, record_id: object) -> DeleteResult:
        self._ensure_open()
        result = self._repository.delete(validation.object_id(record_id))
        logger.info('shelter_operation', extra={'operation': 'delete', 'status': 'success',
                    'deleted_count': result.deleted_count})
        return result

    def close(self) -> None:
        if not self._closed:
            self._repository.close()
            self._closed = True

    def __enter__(self) -> 'AnimalService':
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Type[BaseException] | None, exc: BaseException | None,
                 traceback: TracebackType | None) -> None:
        self.close()
