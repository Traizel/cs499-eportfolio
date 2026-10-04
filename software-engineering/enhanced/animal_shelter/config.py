"""Environment configuration is isolated from domain and database operations."""
import os
import re
from dataclasses import dataclass, field
from typing import Mapping
from .errors import ConfigurationError

@dataclass(frozen=True)
class MongoConfig:
    uri: str = field(repr=False)
    database: str = 'aac'
    collection: str = 'animals'
    timeout_ms: int = 5000

    def __post_init__(self) -> None:
        if not isinstance(self.uri, str) or not self.uri.startswith(('mongodb://', 'mongodb+srv://')):
            raise ConfigurationError('Set MONGODB_URI to a valid MongoDB connection URI.')
        for name in (self.database, self.collection):
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', name):
                raise ConfigurationError('Database and collection names must use 1–64 safe characters.')
        if type(self.timeout_ms) is not int or not 100 <= self.timeout_ms <= 60000:
            raise ConfigurationError('Timeout must be an integer from 100 to 60000 milliseconds.')

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> 'MongoConfig':
        source = os.environ if env is None else env
        try:
            timeout = int(source.get('MONGODB_TIMEOUT_MS', '5000'))
        except (TypeError, ValueError):
            raise ConfigurationError('MONGODB_TIMEOUT_MS must be an integer.') from None
        return cls(source.get('MONGODB_URI', ''), source.get('MONGODB_DATABASE', 'aac'),
                   source.get('MONGODB_COLLECTION', 'animals'), timeout)
