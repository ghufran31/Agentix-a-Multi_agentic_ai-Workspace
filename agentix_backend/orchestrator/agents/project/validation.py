"""Summarize Project validation failures without retaining input values."""
from pydantic import ValidationError

from .schemas import ProjectAgentOutput


_SCHEMA = ProjectAgentOutput.model_json_schema()
_TYPES = {
    dict: 'object', list: 'array', str: 'string', bool: 'boolean',
    int: 'integer', float: 'number', type(None): 'null',
}
RECEIVED_TYPES = frozenset(_TYPES.values()) | {'missing', 'non_json'}


def _resolve(schema):
    if '$ref' in schema:
        return _SCHEMA['$defs'][schema['$ref'].rsplit('/', 1)[-1]]
    return schema


def _expected(schema):
    schema = _resolve(schema)
    if 'anyOf' in schema:
        return ' | '.join(_expected(option) for option in schema['anyOf'])
    if 'enum' in schema:
        return 'enum (' + schema['type'] + ')'
    if schema.get('type') == 'object':
        return schema.get('title', 'object')
    return schema.get('type', 'unknown')


def describe_location(loc):
    """Retain schema fields and array indexes. Replace unknown keys."""
    schema = _SCHEMA
    safe = []
    for part in loc:
        schema = _resolve(schema)
        if 'anyOf' in schema:
            # Project schema unions are nullable fields with one non-null branch.
            schema = _resolve(next(option for option in schema['anyOf'] if option.get('type') != 'null'))
        if isinstance(part, str) and part in schema.get('properties', {}):
            schema = schema['properties'][part]
        elif type(part) is int and part >= 0 and 'items' in schema:
            schema = schema['items']
        else:
            return [*safe, '<unknown>'], 'unknown'
        safe.append(part)
    return safe, _expected(schema)


def validation_issues(exc):
    # LangChain wraps Pydantic's exception as the cause of OutputParserException.
    cause = exc.__cause__
    error = cause if isinstance(cause, ValidationError) else exc
    if not isinstance(error, ValidationError):
        return []
    issues = []
    for item in error.errors(include_url=False, include_context=False)[:12]:
        loc, expected = describe_location(item['loc'])
        category = item['type']
        received = 'missing' if category == 'missing' else _TYPES.get(type(item.get('input')), 'non_json')
        issues.append({'loc': loc, 'type': category, 'expected_type': expected, 'received_type': received})
    return issues
