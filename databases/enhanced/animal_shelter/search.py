"""Public search policy. MongoDB syntax is built here, never supplied by callers."""
from dataclasses import dataclass
from math import isfinite
from . import validation
from .errors import ValidationError

FIELDS = validation.TEXT_FIELDS | validation.NUMBER_FIELDS | {'_id'}
MAX_PAGE_SIZE = 100
MAX_OFFSET = 100000
# Explicit project presets; these are candidate filters, not suitability guarantees.
RESCUES = {
    'water': (('Labrador Retriever Mix', 'Chesapeake Bay Retriever', 'Newfoundland'), 26, 156),
    'mountain': (('German Shepherd', 'Alaskan Malamute', 'Old English Sheepdog',
                  'Siberian Husky', 'Rottweiler'), 26, 156),
    'disaster': (('Doberman Pinscher', 'German Shepherd', 'Golden Retriever',
                  'Bloodhound', 'Rottweiler'), 20, 300),
}

def rescue_query(category):
    if not isinstance(category, str) or category not in RESCUES:
        raise ValidationError('Rescue category must be water, mountain, or disaster.')
    breeds, low, high = RESCUES[category]
    return {'animal_type': 'Dog', 'breed': {'$in': list(breeds)},
            'sex_upon_outcome': 'Intact Male',
            'age_upon_outcome_in_weeks': {'$gte': low, '$lte': high}}

def match(filters, category=None, min_age=None, max_age=None):
    base = validation.document(filters, mode='filter')
    parts = [base] if base else []
    bounds = {}
    for key, value in (('$gte', min_age), ('$lte', max_age)):
        if value is not None:
            if type(value) not in (int, float) or not 0 <= value <= 10000 or not isfinite(value):
                raise ValidationError('Age bounds must be finite numbers from 0 to 10000.')
            bounds[key] = value
    if min_age is not None and max_age is not None and min_age > max_age:
        raise ValidationError('Minimum age cannot exceed maximum age.')
    if bounds:
        parts.append({'age_upon_outcome_in_weeks': bounds})
    if category is not None:
        parts.append(rescue_query(category))
    return {'$and': parts} if len(parts) > 1 else (parts[0] if parts else {})

@dataclass(frozen=True)
class SearchSpec:
    query: dict
    projection: dict | None
    sort: tuple
    page: int
    page_size: int

    @property
    def offset(self):
        return (self.page - 1) * self.page_size

def specification(filters, *, category=None, min_age=None, max_age=None,
                  sort_by='_id', direction=1, fields=None, page=1, page_size=25):
    query = match(filters, category, min_age, max_age)
    if not isinstance(sort_by, str) or sort_by not in FIELDS:
        raise ValidationError('Unsupported sort field.')
    if type(direction) is not int or direction not in (-1, 1):
        raise ValidationError('Sort direction must be 1 or -1.')
    if type(page) is not int or page < 1:
        raise ValidationError('Page must be a positive integer.')
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValidationError('Page size must be an integer from 1 to 100.')
    if (page - 1) * page_size > MAX_OFFSET:
        raise ValidationError('Page offset exceeds 100000; use a narrower search.')
    projection = None
    if fields is not None:
        if (not isinstance(fields, (list, tuple)) or not fields or
            any(not isinstance(f, str) or f not in FIELDS for f in fields)):
            raise ValidationError('Projection must be a nonempty list of approved fields.')
        projection = {f: 1 for f in fields}
        projection['_id'] = 1 if '_id' in fields else 0
    sort = ((sort_by, direction),) if sort_by == '_id' else ((sort_by, direction), ('_id', direction))
    return SearchSpec(query, projection, sort, page, page_size)

def summary_pipeline(filters, *, category=None, min_age=None, max_age=None, limit=100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError('Summary limit must be an integer from 1 to 100.')
    query = match(filters, category, min_age, max_age)
    branches = []
    for label, (breeds, low, high) in RESCUES.items():
        branches.append({'case': {'$and': [
            {'$eq': ['$animal_type', 'Dog']}, {'$in': ['$breed', list(breeds)]},
            {'$eq': ['$sex_upon_outcome', 'Intact Male']},
            {'$isNumber': '$age_upon_outcome_in_weeks'},
            {'$gte': ['$age_upon_outcome_in_weeks', low]},
            {'$lte': ['$age_upon_outcome_in_weeks', high]}]}, 'then': label})
    # With no explicit category, overlaps use water, mountain, disaster precedence.
    category_expression = {'$literal': category} if category else {'$switch': {
        'branches': branches, 'default': 'unclassified'}}
    return [{'$match': query}, {'$group': {
        '_id': {'breed': {'$ifNull': ['$breed', 'Unknown']}, 'category': category_expression},
        'count': {'$sum': 1}}}, {'$sort': {'count': -1, '_id.category': 1, '_id.breed': 1}},
        {'$limit': limit}]
