#!/usr/bin/env python3
"""Publish only latest no-starter, smoke-only runs; never modify source campaigns."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import atomic_json


def read(path):
    return json.loads(path.read_text())


def select(roots):
    latest = {}
    for root in roots:
        for path in sorted((root/'.runs').glob('**/manifest.json')):
            manifest = read(path)
            if (manifest.get('level') not in range(1,6)
                or not manifest.get('started_unix')
                or manifest.get('builder_evaluation_scope') != 'visible_smoke_only'
                or manifest.get('starter_candidate') or manifest.get('starter_sha256')):
                continue
            language = manifest.get('language', 'rust')
            if language not in ('rust', 'cpp'):
                continue
            key = (manifest['level'], language)
            if key not in latest or manifest['started_unix'] > latest[key][1]['started_unix']:
                latest[key] = (path.parent, manifest)
    return latest


def publish(roots, output):
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for (level, language), (run, manifest) in sorted(select(roots).items()):
        state = read(run/'state.json')
        specification = read(run/'specification.json')
        ledger = read(Path(manifest['campaign'])/'ledger.json')
        version = specification.get('version', 'unknown')
        stamp = datetime.fromtimestamp(manifest['started_unix'], timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
        model = manifest.get('model', 'unknown')
        identity = f'{stamp}__stage-{level:02d}__{language}__{model}__{version}__{manifest["fingerprint"][:8]}'
        destination = output/f'stage-{level:02d}'/language
        analyses = [p for p in run.glob('analysis*') if (p/'timeline.json').is_file()]
        analysis = max(analyses, key=lambda p:(p/'timeline.json').stat().st_mtime) if analyses else None
        complete = False
        if analysis is not None and state['finished']:
            timeline = read(analysis/'timeline.json')
            # A partial timeline must not be presented as complete grading.
            tag_dir = run/'repository/.git/refs/tags/release'
            count = len(list(tag_dir.glob('*'))) if tag_dir.exists() else 0
            complete = count > 0 and len(timeline.get('releases', [])) == count
        status = 'graded' if complete else 'builder_finished' if state['finished'] else 'running'
        record = {'id':identity, 'stage':level, 'language':language, 'model':model,
                  'status':status, 'protocol':version, 'framework':manifest['fingerprint'],
                  'started_utc':stamp, 'source_run':str(run),
                  'input_policy':{'starter':False,'feedback':'visible_smoke_only'},
                  'budget_usd':ledger['dollar_limit'], 'wall_seconds':manifest['wall_seconds'],
                  'comparison_policy':'Do not pool different framework fingerprints, languages, models, budgets or input policies.',
                  'path':str(destination.relative_to(output))}
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.publish-', dir=destination.parent) as tmp:
            staging = Path(tmp)/'entry'; staging.mkdir()
            atomic_json(staging/'run.json',record)
            for name in ('manifest.json','specification.json','launch-packet.md'):
                shutil.copyfile(run/name,staging/name)
            if state['finished']:
                for name in ('state.json','progress.md','model-report.md'):
                    if (run/name).is_file():shutil.copyfile(run/name,staging/name)
                # Preserve complete accounting, but never copy API messages or credentials.
                atomic_json(staging/'ledger.json',ledger)
            if complete:
                for p in analysis.iterdir():
                    if p.is_file() and (p.name in ('timeline.json','implementation.bundle','metrics.csv') or p.suffix in ('.png','.svg','.cpp','.rs')):
                        shutil.copyfile(p,staging/p.name)
                    if p.is_dir() and (p/'result.json').is_file() and not 'interrupted' in p.name:
                        shutil.copyfile(p/'result.json',staging/(p.name+'-evaluation.json'))
            (staging/'README.md').write_text(f'# Stage {level} — {language}\n\nLatest eligible run: `{identity}`.\n\nStatus at refresh: **{status}**. Protocol: **{version}**.\nNo starter; only minimal smoke feedback. Budget: ${ledger["dollar_limit"]}; wall ceiling: {manifest["wall_seconds"]} seconds.\n\nSee run.json for provenance and compatibility. This is a snapshot, not a live monitor.\nThe original campaign and private Git repository remain at the recorded source_run.\n')
            if destination.exists():
                if not (destination/'run.json').is_file():
                    raise ValueError(f'Refusing to replace unmanaged directory: {destination}')
                shutil.rmtree(destination)
            staging.rename(destination)
        entries.append(record)
    atomic_json(output/'index.json',{'selection':'Latest started run per stage/language, no starter and smoke-only feedback','runs':entries})
    rows = [f'| {r["stage"]} | {r["language"]} | {r["protocol"]} | {r["status"]} | [{r["started_utc"]}]({r["path"]}/README.md) |' for r in entries]
    (output/'README.md').write_text('# Latest server experiments\n\nOne run per stage and language. Starter-code and comprehensive-feedback runs are excluded.\nThese entries have different evaluator versions: do not pool their scores or performance.\nStages without an eligible run have no result folder. Running entries are snapshots.\n\n| Stage | Language | Protocol | Status | Latest run (UTC) |\n|---|---|---|---|---|\n'+'\n'.join(rows)+'\n\nRefresh using scripts/refresh_results.py with the frozen source worktrees.\nHistorical experiments are preserved in Git history and a local external archive.\nCalibration reports live under diagnostics/, not server results.\n')
    return entries


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,action='append',required=True,help='Frozen repository worktree containing .runs')
    parser.add_argument('--output',type=Path,default=Path('results'))
    args=parser.parse_args()
    print(json.dumps(publish([p.resolve() for p in args.source],args.output.resolve()),indent=2))
