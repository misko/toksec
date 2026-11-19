#!/usr/bin/env python3
"""Plot independently evaluated Git releases against their publication time."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.stages import number as stage_number


def plot(directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory = Path(directory)
    data = json.loads((directory / 'timeline.json').read_text())
    rows = data['releases']
    fig, ax = plt.subplots(figsize=(10, 4))
    times = [r['elapsed_seconds'] / 60 for r in rows]
    counts = [r['passed'] for r in rows]
    end_minutes = max(times[-1] if times else 0, ((data.get('ended_unix') or 0) - (data.get('started_unix') or 0)) / 60)
    ax.step(times + [end_minutes], counts + counts[-1:], where='post', color='#157a6e')
    ax.set_xlim(0, max(1, end_minutes * 1.05))
    if times and times[0] > 0:
        ax.axvspan(0, times[0], color='#eeeeee', zorder=0)
        ax.text(times[0] / 2, .5, 'No tagged submission yet', transform=ax.get_xaxis_transform(), ha='center', va='center', rotation=90, color='#666666', fontsize=8)
    ax.scatter(times, counts, color='#157a6e')
    for x, y, row in zip(times, counts, rows):
        ax.annotate(row['tag'].split('/')[-1], (x, y), xytext=(4, 7), textcoords='offset points', fontsize=8)
    ax.set(xlabel='Release publication: minutes since build started', ylabel='Internal API check groups passed',
           title=f"Stage {stage_number(data)}: tagged releases, independently re-evaluated", ylim=(-0.5, data['total_checks'] + 1.5))
    ax.set_yticks(range(data['total_checks'] + 1))
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(directory / 'correctness.png', dpi=160)
    fig.savefig(directory / 'correctness.svg')
    plt.close(fig)
    names = sorted({name for row in rows for name in row.get('benchmarks', {})})
    fig, axes = plt.subplots(3, 2, figsize=(13, 11), sharex=True)
    metrics = [('median_rps', 'Goodput (valid requests/s)'), ('worst_p99_ms', 'Worst round p99 latency (ms)'),
               ('median_p95_ms', 'Median round p95 latency (ms)'), ('median_cpu_seconds', 'Median server CPU seconds/round'),
               ('failures', 'Failed requests (five rounds)'), ('median_rss_kib', 'Median peak server RSS (KiB)')]
    for ax, (metric, label) in zip(axes.flat, metrics):
        for index, name in enumerate(names):
            color = f'C{index % 10}'
            mode, size, clients = name.rsplit('-', 2)
            workload_label = f'{int(size) // 1024} KiB / {clients} clients ({mode})'
            valid, invalid = [], []
            for row in rows:
                m = row.get('benchmarks', {}).get(name)
                if not m:
                    continue
                value = m.get(metric)
                if value is None and metric in ('median_rss_kib', 'median_cpu_seconds', 'median_p95_ms'):
                    import statistics
                    key = {'median_rss_kib': 'server_peak_rss_kib', 'median_cpu_seconds': 'server_cpu_seconds', 'median_p95_ms': 'p95_ms'}[metric]
                    values = [r[key] for r in m.get('rounds', []) if r.get(key) is not None]
                    value = statistics.median(values) if values else None
                if value is None:
                    continue
                point = (row['elapsed_seconds'] / 60, value)
                (valid if m['eligible'] else invalid).append(point)
            if valid:
                ax.plot(*zip(*valid), marker='o', color=color, label=workload_label)
            if invalid:
                ax.scatter(*zip(*invalid), marker='x', color=color, label=workload_label + ' (ineligible)')
        ax.set_ylabel(label)
        ax.set_xlim(0, max(1, end_minutes * 1.05))
        ax.grid(alpha=.2)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=7)
        else:
            ax.text(.5, .5, 'No measurements available', ha='center', transform=ax.transAxes)
    for ax in axes[-1]:
        ax.set_xlabel('Release publication: minutes since build started')
    fig.suptitle('Post-run measurements of tagged source; crosses are ineligible, not evidence of improvement')
    fig.tight_layout()
    fig.savefig(directory / 'performance.png', dpi=160)
    fig.savefig(directory / 'performance.svg')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    plot(parser.parse_args().directory)
