"""Explicit results preserve the difference between success, no match and failure."""
from dataclasses import dataclass
from typing import Any

Document = dict[str, Any]

@dataclass(frozen=True)
class CreateResult:
    inserted_id: str

@dataclass(frozen=True)
class ReadResult:
    records: tuple[Document, ...]
    truncated: bool = False

@dataclass(frozen=True)
class UpdateResult:
    matched_count: int
    modified_count: int

@dataclass(frozen=True)
class DeleteResult:
    deleted_count: int
