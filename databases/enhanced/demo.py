"""Run a deterministic offline workflow with synthetic animal records."""
from animal_shelter import AnimalService, ValidationError
from animal_shelter.memory_repository import MemoryAnimalRepository


def main() -> None:
    with AnimalService(MemoryAnimalRepository()) as shelter:
        created = shelter.create({'animal_id': 'DEMO001', 'animal_type': 'Dog', 'name': 'Scout'})
        print('Created synthetic record:', bool(created.inserted_id))
        print('Read matching records:', len(shelter.read({'animal_type': 'Dog'}).records))
        print('Changed name:', shelter.update(created.inserted_id, {'name': 'Scout II'}))
        print('Repeated same update:', shelter.update(created.inserted_id, {'name': 'Scout II'}))
        try:
            shelter.read({'animal_type': {'$ne': None}})
        except ValidationError:
            print('Rejected nested query operator: True')
        print('Deleted record:', shelter.delete(created.inserted_id))
        print('Read after deletion:', len(shelter.read({}).records))
    print('Context manager closed the service.')

if __name__ == '__main__':
    main()
