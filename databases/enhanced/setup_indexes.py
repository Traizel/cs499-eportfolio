"""Deployment action: create the package index on the configured collection."""
from animal_shelter.config import MongoConfig
from animal_shelter.database_repository import DatabaseRepository

repo = DatabaseRepository.connect(MongoConfig.from_env())
try:
    print('Existing index names:', [x['name'] for x in repo.list_indexes()])
    print('Ensured index:', repo.ensure_indexes())
finally:
    repo.close()
