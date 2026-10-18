"""Live functional checks and explain comparison on a new disposable collection.

Uses MONGODB_URI; never reads, clears, or modifies the AAC animals collection.
Writes only a uniquely named collection under cs499_verification; drops it on exit.
"""
import json
import os
from pathlib import Path
from uuid import uuid4
from bson import ObjectId
from animal_shelter.config import MongoConfig
from animal_shelter.database_repository import DatabaseRepository, INDEX_NAME
from animal_shelter.database_service import DatabaseService
from animal_shelter.search import specification

def stages(value):
    result = set()
    if isinstance(value, dict):
        if 'stage' in value:
            result.add(value['stage'])
        for child in value.values():
            result.update(stages(child))
    elif isinstance(value, list):
        for child in value:
            result.update(stages(child))
    return sorted(result)

def metrics(plan):
    stats = plan['executionStats']
    return {**{k: stats[k] for k in ('nReturned', 'totalDocsExamined',
             'totalKeysExamined', 'executionTimeMillis')}, 'stages': stages(stats['executionStages'])}

def run(output):
    collection_name = 'verify_' + uuid4().hex
    config = MongoConfig(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017/'),
                         'cs499_verification', collection_name, 10000)
    repo = DatabaseRepository.connect(config)
    collection = repo._collection  # Trusted administrative fixture setup.
    try:
        documents = []
        for i in range(10000):
            candidate = i % 100 == 0
            documents.append({'_id': ObjectId(f'{i + 1:024x}'), 'animal_id': f'DEMO{i:05}',
                'animal_type': 'Dog' if candidate else 'Cat',
                'breed': 'Labrador Retriever Mix' if candidate else 'Domestic Shorthair',
                'sex_upon_outcome': 'Intact Male' if candidate else 'Spayed Female',
                'age_upon_outcome_in_weeks': 52, 'name': 'Demo', 'color': 'Black'})
        collection.insert_many(documents)
        service = DatabaseService(repo)
        checks = []
        before_indexes = repo.list_indexes()
        spec = specification({}, category='water', sort_by='age_upon_outcome_in_weeks',
                             fields=['animal_id', 'breed'], page_size=100)
        expected = tuple({'animal_id': x['animal_id'], 'breed': x['breed']}
                         for x in documents if x['animal_type'] == 'Dog')
        before_records = repo.search(spec).records
        assert before_records == expected
        before = repo.explain(spec)  # No package index exists yet.
        natural = repo.explain(spec, hint='natural')
        repo.ensure_indexes()
        repo.ensure_indexes()  # Idempotence.
        after = repo.explain(spec)
        hinted = repo.explain(spec, hint=INDEX_NAME)
        assert repo.search(spec).records == before_records
        checks.append('Same 100 candidate records and projection before and after indexing')
        gathered = []
        for page in range(1, 8):
            result = service.search(category='water', sort_by='breed', fields=['animal_id'],
                                    page=page, page_size=17)
            gathered.extend(x['animal_id'] for x in result.records)
            assert result.has_next == (page < 6)
        assert gathered == [x['animal_id'] for x in expected]
        checks.append('Stable pages have no duplicates or omissions; last and empty pages verified')
        assert service.search({'animal_type': 'Cat'}, category='water').records == ()
        checks.append('Contradictory validated filters return no candidates')
        water = service.rescue_summary(category='water')
        assert water == ({'_id': {'breed': 'Labrador Retriever Mix', 'category': 'water'}, 'count': 100},)
        all_summary = service.rescue_summary()
        assert sum(x['count'] for x in all_summary) == 10000
        assert {x['_id']['category']: x['count'] for x in all_summary} == {'unclassified': 9900, 'water': 100}
        checks.append('Server aggregation returns exact counts with and without category filters')
        # Add policy boundaries and overlapping breeds after performance measurements.
        collection.insert_many([
            {'animal_type': 'Dog', 'breed': 'Newfoundland', 'sex_upon_outcome': 'Intact Male',
             'age_upon_outcome_in_weeks': age, 'animal_id': f'BOUND{age}'} for age in (25, 26, 156, 157)])
        assert len(service.search({'breed': 'Newfoundland'}, category='water').records) == 2
        collection.insert_one({'animal_type': 'Dog', 'breed': 'German Shepherd',
            'sex_upon_outcome': 'Intact Male', 'age_upon_outcome_in_weeks': 52, 'animal_id': 'OVERLAP'})
        assert service.rescue_summary({'animal_id': 'OVERLAP'})[0]['_id']['category'] == 'mountain'
        assert service.rescue_summary({'animal_id': 'OVERLAP'}, category='disaster')[0]['_id']['category'] == 'disaster'
        checks.append('Inclusive age boundaries and documented overlap precedence verified')
        data = {'server_version': repo._client.server_info()['version'], 'driver': __import__('pymongo').version,
                'fixture_records': 10000, 'fixture': 'Generated data; not the AAC dataset',
                'checks': checks, 'indexes_before': before_indexes, 'indexes_after': repo.list_indexes(),
                'metrics': {label: metrics(plan) for label, plan in (
                    ('before_unhinted', before), ('natural_scan_control', natural),
                    ('after_unhinted', after), ('index_hint_control', hinted))},
                'limitations': ['Single selective synthetic workload; not a production benchmark',
                    'Explain bypasses plan cache; millisecond timings can round to zero',
                    'Indexes do not accelerate every sort; offset pagination slows with depth']}
        Path(output).write_text(json.dumps(data, indent=2, default=str) + '\n')
        print(json.dumps(data, indent=2, default=str))
    finally:
        collection.drop()
        repo.close()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='live_results.json')
    run(parser.parse_args().output)
