from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    minimum: int
    description: str
    execute: object


def registry():
    cases = []
    def case(identity, minimum, description):
        def register(function):
            cases.append(Case(identity, minimum, description, function))
            return function
        return register
    return cases, case
