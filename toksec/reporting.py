"""Read-only, reproducible run report; does not require a current framework hash."""
import json
from pathlib import Path
from decimal import Decimal
from toksec.stages import number as stage_number


def markdown(run):
    from toksec.stage_dispatch import stage_of
    if stage_of(run) == 10:
        from toksec.controller import counted_capacity as capacity, read
        state = read(run)
        cap = capacity(run)
        tag = state['tags'][-1]['tag'] if state['tags'] else 'none'
        return ('# Stage 10 implementation report\n\n'
                'API coverage: partial. Performance: provisional; no final acceptance grade.\n\n'
                f'Last completed tag: {tag}. Published releases: {len(state["tags"])}.\n'
                f'Finished: {state["finished"]}.\n'
                f'Conservative model spend: ${cap["budget"]["spent_usd_upper_bound"]:.8f}.\n')
    run = Path(run)
    read = lambda p: json.loads(p.read_text())
    manifest, state = read(run/'manifest.json'), read(run/'state.json')
    ledger = read(Path(manifest['campaign'])/'ledger.json')
    requests = [r for r in ledger['requests'] if r.get('run') == run.name]
    settled = [r['usage'] for r in requests if r['state'] == 'settled']
    spent = sum((Decimal(u['cost_usd_upper_bound']) for u in settled), Decimal(0))
    lines = [f"# Stage {stage_number(manifest)}: {run.name}", '',
             f"Model: {manifest.get('model', 'gpt-6-luna')}; finished: {state['finished']}; retained: {state['best']}",
             f"Calls: {len(requests)}; tokens: {sum(u['total'] for u in settled)}; cost upper bound: ${spent}", '',
             '| Candidate | Passed checks | Build | Retained |', '|---|---:|---|---|']
    for p in sorted(run.glob('candidates/*/report.json'), key=lambda p:p.stat().st_mtime):
        r=read(p);cases=r['checks'].get('cases',[])
        lines.append(f"| {r['id'][:12]} | {sum(c['passed'] for c in cases)}/{len(cases)} | {r['build']['passed']} | {r['id']==state['best']} |")
    lines += ['', '| Measurement | Candidate | Workload | Median req/s | Worst p99 ms | Failures | Eligible | Promoted |', '|---|---|---|---:|---:|---:|---|---|']
    records = sorted(run.glob('benchmarks/*.json'),key=lambda p:read(p).get('recorded_unix',0))
    if not records: records=sorted(run.glob('candidates/*/benchmark.json'))
    decisions=[]
    for n,p in enumerate(records,1):
        r=read(p)
        for candidate,workloads in r['summaries'].items():
            for name,m in workloads.items():
                lines.append(f"| {n} | {candidate[:12]} | {name} | {m['median_rps']:.1f} | {m['worst_p99_ms']} | {m['failures']} | {m['eligible']} | {r['decision']['promote'] and candidate==r['candidate']} |")
        decisions.append(f"Measurement {n}: {r['decision']['reason']}")
    lines += [''] + decisions
    from toksec.releases import list_releases
    tagged=list_releases(run)
    lines += ['', 'Graded release: ' + (tagged[-1]['tag'] + ' at ' + tagged[-1]['commit'] if tagged else 'none')]
    lines += ['', 'Ineligible measurements do not establish a performance improvement. Full round metrics are preserved in benchmarks/*.json.']
    return '\n'.join(lines)
