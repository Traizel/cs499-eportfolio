"""Read-only demo using configured AAC data; index setup is a separate action."""
import json
from animal_shelter.config import MongoConfig
from animal_shelter.database_repository import DatabaseRepository
from animal_shelter.database_service import DatabaseService

with DatabaseService(DatabaseRepository.connect(MongoConfig.from_env())) as service:
    page = service.search(category='water', fields=['animal_id', 'breed', 'age_upon_outcome_in_weeks'],
                          sort_by='age_upon_outcome_in_weeks', page_size=10)
    print(json.dumps({'records': page.records, 'has_next': page.has_next,
                      'summary': service.rescue_summary(category='water')}, indent=2, default=str))
