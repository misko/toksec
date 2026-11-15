"""Versioned builder and parent-evaluation contracts, validated at file boundaries."""
import hashlib
import json
import math
from pathlib import Path
import re

from toksec.storage import atomic_json

CONTRACTS = Path(__file__).resolve().parents[1] / 'contracts'
KEYWORDS = frozenset({
    '$schema', 'title', 'description', 'type', 'properties', 'required',
    'additionalProperties', 'const', 'enum', 'minimum', 'maximum', 'minLength',
    'pattern', 'items', 'minItems', 'maxItems', 'uniqueItems', 'allOf', 'anyOf',
    'if', 'then', 'else',
})


def _same(left, right):
    return type(left) is type(right) and left == right


def _validate(value, schema, path='$'):
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ValueError(f'{path}: unsupported schema keywords {sorted(unknown)}')
    kinds = schema.get('type')
    kinds = [kinds] if isinstance(kinds, str) else kinds
    if kinds is not None:
        types = {'object': dict, 'array': list, 'string': str, 'integer': int,
                 'number': (int, float), 'boolean': bool, 'null': type(None)}
        if any(k not in types for k in kinds):
            raise ValueError(f'{path}: unsupported schema type')
        if not any((type(value) in types[k] if isinstance(types[k], tuple)
                    else type(value) is types[k]) for k in kinds):
            raise ValueError(f'{path}: expected {kinds}')
    if 'const' in schema and not _same(value, schema['const']):
        raise ValueError(f'{path}: unexpected constant')
    if 'enum' in schema and not any(_same(value, item) for item in schema['enum']):
        raise ValueError(f'{path}: unexpected enum value')
    if type(value) in (int, float):
        if type(value) is float and not math.isfinite(value):
            raise ValueError(f'{path}: nonfinite number')
        if 'minimum' in schema and value < schema['minimum']:
            raise ValueError(f'{path}: below minimum')
        if 'maximum' in schema and value > schema['maximum']:
            raise ValueError(f'{path}: above maximum')
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0):
            raise ValueError(f'{path}: string too short')
        if 'pattern' in schema and re.search(schema['pattern'], value) is None:
            raise ValueError(f'{path}: invalid string format')
    if isinstance(value, dict):
        missing = set(schema.get('required', [])) - value.keys()
        if missing:
            raise ValueError(f'{path}: missing fields {sorted(missing)}')
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value) - properties.keys():
            raise ValueError(f'{path}: unexpected fields {sorted(set(value)-properties.keys())}')
        for key, child in properties.items():
            if key in value:
                _validate(value[key], child, f'{path}.{key}')
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', len(value)):
            raise ValueError(f'{path}: invalid item count')
        if schema.get('uniqueItems') and any(value[i] == value[j] for i in range(len(value)) for j in range(i)):
            raise ValueError(f'{path}: duplicate items')
        if 'items' in schema:
            for index, item in enumerate(value):
                _validate(item, schema['items'], f'{path}[{index}]')
    for child in schema.get('allOf', []):
        _validate(value, child, path)
    if 'anyOf' in schema:
        for child in schema['anyOf']:
            try:
                _validate(value, child, path)
                break
            except ValueError:
                pass
        else:
            raise ValueError(f'{path}: no schema alternative matches')
    if 'if' in schema:
        try:
            _validate(value, schema['if'], path)
        except ValueError:
            branch = 'else'
        else:
            branch = 'then'
        if branch in schema:
            _validate(value, schema[branch], path)


def _check_schema(schema):
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ValueError(f'unsupported schema keywords {sorted(unknown)}')
    for child in schema.get('properties', {}).values():
        _check_schema(child)
    for key in ('items', 'if', 'then', 'else'):
        if key in schema:
            _check_schema(schema[key])
    for key in ('allOf', 'anyOf'):
        for child in schema.get(key, []):
            _check_schema(child)


def _validated(value, name):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError('contract must contain JSON values') from error
    schema = json.loads((CONTRACTS / (name + '.schema.json')).read_text())
    _check_schema(schema)
    _validate(value, schema)
    return value


def artifact_contract(stage, language):
    contract = {
        'schema_version': 1, 'stage': stage, 'language': language,
        'submission': {'source_file': 'main.cpp' if language == 'cpp' else 'main.rs',
                       'encoding': 'utf-8', 'max_bytes': 1048576},
        'release': {'tag_pattern': '^release/[0-9]{6}$',
                    'selection': 'last_completed_tag', 'metadata_owner': 'controller'},
    }
    return validate_artifact(contract)


def validate_artifact(contract):
    return _validated(contract, 'artifact')


def write_artifact(run, stage, language):
    run = Path(run)
    contract = artifact_contract(stage, language)
    (run / 'builder-inputs').mkdir(parents=True, exist_ok=True)
    atomic_json(run / 'artifact.json', contract)
    atomic_json(run / 'builder-inputs/artifact.json', contract)
    return contract


def read_artifact(run, stage, language, expected_sha256=None):
    path = Path(run) / 'artifact.json'
    if not path.exists() and expected_sha256 is None:
        return artifact_contract(stage, language)
    raw = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('frozen artifact contract hash mismatch')
    contract = validate_artifact(json.loads(raw))
    if (contract['stage'], contract['language']) != (stage, language):
        raise ValueError('artifact contract stage/language mismatch')
    return contract


def validate_source(source, contract):
    validate_artifact(contract)
    if not isinstance(source, str):
        raise ValueError('source must be UTF-8 text')
    try:
        encoded = source.encode(contract['submission']['encoding'])
    except UnicodeEncodeError as error:
        raise ValueError('source must be valid UTF-8 text') from error
    if len(encoded) > contract['submission']['max_bytes']:
        raise ValueError('source exceeds artifact contract byte limit')
    return source


def validate_evaluation(evaluation):
    _validated(evaluation, 'evaluation')
    api = evaluation['api']
    passed, total = api['passed'], api['total']
    if passed is not None and total is not None:
        if passed > total:
            raise ValueError('API passed count exceeds total')
        if api['status'] == 'passed' and (total == 0 or passed != total):
            raise ValueError('passed API requires all nonempty cases to pass')
    if api['status'] == 'passed' and (passed is None or total is None):
        raise ValueError('passed API requires case counts')
    return evaluation
