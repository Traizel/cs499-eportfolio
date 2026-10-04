"""A deliberately narrow, equality-only AAC service boundary.

Supported fields can be extended here with explicit types. Raw MongoDB operators,
arrays and nested documents are never accepted through the public service API.
"""
import math
from bson import ObjectId
from .errors import ValidationError
from .models import Document

TEXT_FIELDS = frozenset({'animal_id', 'animal_type', 'breed', 'name', 'color',
    'sex_upon_outcome', 'outcome_type', 'outcome_subtype', 'date_of_birth',
    'datetime', 'monthyear', 'age_upon_outcome'})
NUMBER_FIELDS = frozenset({'age_upon_outcome_in_weeks', 'location_lat', 'location_long'})
REQUIRED_FIELDS = frozenset({'animal_id', 'animal_type'})
MAX_TEXT_LENGTH = 256
MAX_RESULTS = 1000


def object_id(value: object) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    raise ValidationError('Record id must be a valid 24-character MongoDB ObjectId.')


def document(value: object, *, mode: str) -> Document:
    """Return a new validated dictionary; never mutate caller-owned input."""
    if mode not in {'create', 'update', 'filter'}:
        raise ValueError('Unknown validation mode.')
    if not isinstance(value, dict) or (not value and mode != 'filter'):
        raise ValidationError('Expected a nonempty dictionary (empty read filters are allowed).')
    allowed = TEXT_FIELDS | NUMBER_FIELDS | ({'_id'} if mode == 'filter' else set())
    result: Document = {}
    for key, item in value.items():
        if not isinstance(key, str) or key not in allowed:
            raise ValidationError('An unsupported field or query operator was provided.')
        if key == '_id':
            result[key] = object_id(item)
        elif key in TEXT_FIELDS:
            if not isinstance(item, str) or len(item) > MAX_TEXT_LENGTH or '\x00' in item:
                raise ValidationError('Text fields must be strings of at most 256 characters without NUL.')
            if key in REQUIRED_FIELDS and not item.strip():
                raise ValidationError('Animal id and animal type cannot be blank.')
            result[key] = item
        else:
            # bool is a subclass of int, but not a valid measurement.
            if type(item) not in (int, float):
                raise ValidationError('Measurement fields must be finite numbers.')
            try:
                finite = math.isfinite(item)
            except OverflowError:
                finite = False
            if not finite:
                raise ValidationError('Measurement fields must be finite numbers.')
            low, high = (0, 10000) if key == 'age_upon_outcome_in_weeks' else ((-90, 90) if key == 'location_lat' else (-180, 180))
            if not low <= item <= high:
                raise ValidationError('Measurement is outside the supported range.')
            result[key] = item
    if mode == 'create' and not REQUIRED_FIELDS.issubset(result):
        raise ValidationError('Create requires animal_id and animal_type.')
    return result


def result_limit(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_RESULTS:
        raise ValidationError('Read limit must be an integer from 1 to 1000.')
    return value
