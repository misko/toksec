"""Check the content invariants a security envelope hash cannot prove.

`verify()` recomputes digests, so it proves the recorded bytes are unchanged. It
says nothing about whether the report agrees with the envelope, cites real source
lines, or carries the required sections. These checks run before recording and in
CI over published results.
"""
import json
import re
from pathlib import Path

SECTIONS = ('## Audit narrative', '## Findings table', '## Artifact index')
SEVERITIES = ('informational', 'low', 'medium', 'high', 'critical')
ROW = re.compile(r'^\|\s*(SEC-\d{3})\s*\|(.*)\|\s*$', re.MULTILINE)
CITATION = re.compile(r'line\s+(\d+)(?:\s*\(`?([A-Za-z_][A-Za-z0-9_]*)`?)?')


def _cells(row):
    return [cell.strip().strip('`') for cell in row.split('|')]


def _table(report_text):
    start = report_text.find('## Findings table')
    if start < 0:
        return {}, []
    section = report_text[start:]
    end = section.find('\n## ', 1)
    section = section if end < 0 else section[:end]
    rows = {}
    columns = []
    for line in section.split('\n'):
        if not line.startswith('|'):
            continue
        if not columns:
            columns = _cells(line.strip('|'))
        elif set(line) <= set('|-: '):
            continue
        else:
            cells = _cells(line.strip('|'))
            if cells and re.fullmatch(r'SEC-\d{3}', cells[0]):
                rows[cells[0]] = cells
    return rows, columns


def lint(report_text, findings, source_lines, required=()):
    """Return a list of human-readable defects; empty means the report is sound.

    ``required`` are regexes at least one finding title must match. Self-consistency
    cannot catch a coverage gap: dropping a finding from both the envelope and the
    report leaves the two in agreement while the defect disappears, so callers pass
    the titles a class of run is expected to carry.
    """
    problems = []
    # A stub report with no second-level headings is accepted as unstructured;
    # any structured report must carry the reviewed sections and a real table.
    structured = '\n## ' in report_text
    if structured:
        for section in SECTIONS:
            if section not in report_text:
                problems.append(f'missing section: {section}')

    rows, columns = _table(report_text)
    recorded = {finding['id']: finding for finding in findings}
    if not structured:
        return problems + _citations(report_text, source_lines)
    for missing in sorted(set(recorded) - set(rows)):
        problems.append(f'finding absent from table: {missing}')
    for extra in sorted(set(rows) - set(recorded)):
        problems.append(f'table row has no finding record: {extra}')

    if not columns and recorded:
        problems.append('envelope records findings but the report has no findings table')
    elif 'Severity' not in columns:
        problems.append('findings table has no Severity column')
    elif recorded:
        index = columns.index('Severity')
        for finding_id, cells in rows.items():
            value = cells[index] if index < len(cells) else ''
            if value not in SEVERITIES:
                problems.append(f'{finding_id}: table severity {value!r} not in enum')
            elif finding_id in recorded and value != recorded[finding_id]['severity']:
                problems.append(f"{finding_id}: table severity {value!r} differs from record "
                                f"{recorded[finding_id]['severity']!r}")

    for pattern in required:
        if not any(re.search(pattern, finding.get('title', ''), re.I) for finding in findings):
            problems.append(f'no finding matches required pattern {pattern!r}')

    for finding_id, finding in recorded.items():
        for name in finding['evidence']:
            if name not in report_text:
                problems.append(f'{finding_id}: evidence not cited in report: {name}')

    return problems + _citations(report_text, source_lines)


def _citations(report_text, source_lines):
    if source_lines is None:
        # No source was ever produced (builder timed out). Line citations cannot be
        # resolved, but one naming a line anyway is a report bug worth failing on.
        return ([f'line {m.group(1)} cited but the run produced no source'
                 for m in CITATION.finditer(report_text)])
    problems = []
    for match in CITATION.finditer(report_text):
        line, symbol = int(match.group(1)), match.group(2)
        if not 1 <= line <= len(source_lines):
            problems.append(f'line {line} outside source (1-{len(source_lines)})')
            continue
        body = source_lines[line - 1]
        if not body.strip() or body.strip() in ('{', '}'):
            problems.append(f'line {line} is blank or a brace')
        elif symbol and symbol not in body:
            problems.append(f'line {line} does not contain {symbol!r}')
    return problems


def lint_directory(directory, source_text, required=()):
    """Lint one recorded evaluation directory against the tagged source.

    ``source_text`` may be None for a run that produced no source at all.
    """
    directory = Path(directory)
    record = json.loads((directory / 'evaluation.json').read_text())
    if record.get('kind') != 'security':
        return []
    return lint((directory / 'report.md').read_text(), record['findings'],
                None if source_text is None else source_text.split('\n'), required)
