"""Optional read-only smoke check against the user's configured MongoDB."""
from animal_shelter import AnimalService, ShelterError
from animal_shelter.config import MongoConfig
from animal_shelter.mongo_repository import MongoAnimalRepository


def main() -> int:
    try:
        with AnimalService(MongoAnimalRepository.connect(MongoConfig.from_env())) as shelter:
            result = shelter.read({}, limit=5)
            print(f'Connected. Returned {len(result.records)} records; truncated={result.truncated}.')
        return 0
    except ShelterError as error:
        print(f'Controlled error: {error}')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
