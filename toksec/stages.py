"""Canonical stage identity with read compatibility for historical level fields."""
import importlib

SUPPORTED_STAGES = (1, 2, 3, 4, 5, 10)


def number(value):
    if isinstance(value, dict):
        stage = value.get('stage', value.get('level'))
        if 'stage' in value and 'level' in value and (
                type(value['level']) is not int or value['level'] != stage):
            raise ValueError('conflicting stage identities')
    else:
        stage = value
    if type(stage) is not int or stage < 1:
        raise ValueError('stage must be a positive integer')
    return stage


def identifier(value):
    return f'stage-{number(value):02d}'


def title(value):
    return f'Stage {number(value)}'


def module(value, component):
    stage = number(value)
    if stage not in SUPPORTED_STAGES:
        raise ValueError('unsupported stage identity')
    if component not in ('api', 'checks', 'performance', 'packet'):
        raise ValueError('unsupported stage component')
    location = component if component == 'packet' else f'grading.{component}'
    return importlib.import_module(f'stages.{identifier(stage)}.{location}')
