#!/usr/bin/env python3
"""Re-check published security reports against their envelopes and tagged source."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.releases import git  # noqa: E402
from toksec.security_report_lint import lint_directory  # noqa: E402
from toksec.result_storage import read  # noqa: E402


SOURCE_NAMES = ('main.cpp', 'main.rs')


def archived_source(run, commit=None, root=None):
    """The tagged or archived source file, whichever language the run used."""
    for name in SOURCE_NAMES:
        if run is not None:
            try:
                return git(run, 'show', f'{commit}:{name}')
            except subprocess.CalledProcessError:
                continue
        if root is not None and (root / name).is_file():
            return (root / name).read_text()
    return None


def source_run(results, name):
    """The raw run for a published run id, or None when none keeps a repository.

    Raw runs live either directly under `.runs/<name>` or nested beneath a batch
    directory, depending on how the batch was launched.
    """
    root = Path(results).resolve().parent / '.runs'
    for candidate in root.rglob(name):
        if candidate.is_dir() and (candidate / 'repository').is_dir():
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path('results'))
    parser.add_argument('--require', action='append', metavar='REGEX', default=[],
                        help='finding title regex every registered envelope must carry '
                             '(repeatable); catches a coverage gap that self-consistency '
                             'cannot, such as a family-wide defect missing from one report')
    args = parser.parse_args()
    failed = 0
    directories = sorted(
        directory for directory in args.results.glob('*/evaluation/security-*')
        if (directory.parent.parent / 'run.json').is_file())

    for directory in directories:
        envelope = directory / 'evaluation.json'
        if not envelope.is_file():
            print(f'{directory}: unregistered report')
            failed += 1
            continue
        record = read(envelope)
        tag = record['release']['tag']
        if tag is None:
            # A run with no release has no tag to read source from; use the raw run
            # tree if the builder left one, else lint without citations.
            run = source_run(args.results, directory.parent.parent.name)
            source = archived_source(None, root=run / 'repository' if run else None)
        elif not re.fullmatch(r'release/[0-9]{6}', tag):
            print(f'{directory}: bad release tag')
            failed += 1
            continue
        else:
            run = source_run(args.results, directory.parent.parent.name)
            # A report-only packet preserves the source but keeps no repository.
            source = archived_source(run, record['release']['commit'],
                                     directory.parent.parent / 'implementation/source')
            # Nothing to resolve citations against; structural checks still run.
        # A run with no release has no source to analyse, so a source-level
        # pattern only binds the envelopes that pinned a tag.
        defects = lint_directory(directory, source,
                                 args.require if tag is not None else ())
        if defects:
            failed += 1
            print('\n'.join(f'{directory}: {defect}' for defect in defects))
    print(f'{len(directories) - failed}/{len(directories)} security reports pass')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
