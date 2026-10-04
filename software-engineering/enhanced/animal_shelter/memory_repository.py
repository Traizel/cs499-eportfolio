"""Offline demo/test adapter. Not persistent and not a MongoDB emulator."""
from copy import deepcopy
from bson import ObjectId
from .errors import ResourceClosedError
from .models import Document, CreateResult, ReadResult, UpdateResult, DeleteResult

class MemoryAnimalRepository:
    def __init__(self) -> None:
        self._records: dict[ObjectId, Document] = {}
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ResourceClosedError('Memory repository is closed.')

    def create(self, data: Document) -> CreateResult:
        self._ensure_open()
        identity = ObjectId()
        self._records[identity] = {**deepcopy(data), '_id': identity}
        return CreateResult(str(identity))

    def read(self, filters: Document, limit: int) -> ReadResult:
        self._ensure_open()
        records = []
        for row in self._records.values():
            if all(row.get(key) == value for key, value in filters.items()):
                records.append(deepcopy(row))
                if len(records) > limit:
                    break
        return ReadResult(tuple(records[:limit]), len(records) > limit)

    def update(self, record_id: ObjectId, changes: Document) -> UpdateResult:
        self._ensure_open()
        record = self._records.get(record_id)
        if record is None:
            return UpdateResult(0, 0)
        modified = any(record.get(key) != value for key, value in changes.items())
        record.update(deepcopy(changes))
        return UpdateResult(1, int(modified))

    def delete(self, record_id: ObjectId) -> DeleteResult:
        self._ensure_open()
        return DeleteResult(int(self._records.pop(record_id, None) is not None))

    def close(self) -> None:
        self._closed = True
