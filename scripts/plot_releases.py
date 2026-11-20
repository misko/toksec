#!/usr/bin/env python3
"""Plot independently evaluated Git releases by elapsed time and settled spend."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stages.common.grading.performance import Workload
from toksec import benchmark
from toksec.specification import workloads
from toksec.stages import number as stage_number


STATUS_COLORS = {
    'Qualified': '#007c66',
    'Request failures': '#ac3434',
    'Infrastructure or effects': '#9b6415',
    'Failures and other issues': '#7d3a8e',
    'Incomplete evidence': '#637291',
    'Calibration excluded': '#946130',
    'API gate failed': '#ad4932',
    'Provisional': '#496d8d',
    'Unavailable': '#819099',
}
METRICS = (
    ('median_rps', 'Valid requests per second'),
    ('median_p95_ms', 'Median round p95 (ms)'),
    ('worst_p99_ms', 'Worst round p99 (ms)'),
)
FIELDS = (
    'run_id', 'tag', 'commit', 'source_sha256', 'evaluation_id',
    'elapsed_seconds', 'settled_usd_upper_bound', 'held_usd',
    'api_passed', 'api_total', 'api_status', 'workload', 'qualification', 'issues',
    'round_count', 'failures', 'timeouts', 'median_rps', 'median_p95_ms', 'worst_p99_ms',
    'median_payload_bytes_per_second', 'median_server_cpu_seconds', 'max_server_peak_rss_kib',
    'generator_saturated_rounds', 'upstream_saturated_rounds',
)


def number(value):
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError('timeline contains an invalid elapsed time, spend or measurement')
    return result


def declared_workloads(data):
    if 'workloads' in data:
        return {w['id']: Workload(**w) for w in data['workloads']}
    if stage_number(data) == 10:
        return {}
    return {w.id: w for w in workloads(stage_number(data))}


def api_status(row, total):
    if row.get('api_status'):
        return row['api_status']
    if row.get('passed') is None:
        return 'not_run'
    if row.get('build_passed') is False or row['passed'] != total:
        return 'failed'
    return 'passed'


def classify(summary, workload, api, provisional):
    if api == 'failed':
        return 'API gate failed', ['api_failed']
    if provisional:
        return 'Provisional', ['partial_coverage']
    if api != 'passed':
        return 'Unavailable', ['api_' + api]
    if summary is None:
        return 'Unavailable', ['missing_measurement']
    if workload is None:
        return 'Unavailable', ['undeclared_workload']
    issues = benchmark.cell_issues(summary, workload)
    if not issues:
        return 'Qualified', []
    bad_requests = {'request_failures', 'timeouts'} & set(issues)
    other_issues = set(issues) - {'request_failures', 'timeouts', 'no_valid_delivery'}
    if bad_requests:
        return ('Failures and other issues' if other_issues else 'Request failures'), issues
    if 'calibration_unqualified' in issues:
        return 'Calibration excluded', issues
    if {'incomplete_rounds', 'missing_measurement', 'mismatched_summary', 'invalid_counts', 'missing_samples'} & set(issues):
        return 'Incomplete evidence', issues
    return 'Infrastructure or effects', issues


def round_stat(rounds, key, aggregate):
    if rounds and all(r.get(key) is not None for r in rounds):
        return aggregate(r[key] for r in rounds)
    return None


def observations(data, declared):
    releases = data['releases']
    names = sorted(set(declared).union(*(set(r.get('benchmarks') or {}) for r in releases)))
    rows = []
    for release in releases:
        api = api_status(release, data['total_checks'])
        capacity = release.get('capacity') or {}
        total = data['total_checks']
        for name in names:
            summary = (release.get('benchmarks') or {}).get(name)
            provisional = (stage_number(data) == 10 or release.get('coverage') == 'partial'
                           or release.get('performance_status') == 'provisional')
            status, issues = classify(summary, declared.get(name), api, provisional)
            summary = summary or {}
            rounds = summary.get('rounds') or []
            good = status == 'Qualified'
            rows.append({
                'run_id': data.get('run_id'), 'tag': release['tag'], 'commit': release.get('commit'),
                'source_sha256': release.get('source_sha256'), 'evaluation_id': release.get('evaluation_id'),
                'elapsed_seconds': release.get('elapsed_seconds'),
                'settled_usd_upper_bound': capacity.get('spent_usd_upper_bound'),
                'held_usd': capacity.get('reserved_usd'), 'api_passed': release.get('passed'),
                'api_total': total, 'api_status': api, 'workload': name, 'qualification': status,
                'issues': ','.join(issues), 'round_count': len(rounds) if summary else None,
                'failures': summary.get('failures'), 'timeouts': round_stat(rounds, 'timeouts', sum),
                'median_rps': summary.get('median_rps') if good else None,
                'median_p95_ms': round_stat(rounds, 'p95_ms', statistics.median) if good else None,
                'worst_p99_ms': summary.get('worst_p99_ms') if good else None,
                'median_payload_bytes_per_second': round_stat(rounds, 'bytes_per_second', statistics.median),
                'median_server_cpu_seconds': round_stat(rounds, 'server_cpu_seconds', statistics.median),
                'max_server_peak_rss_kib': round_stat(rounds, 'server_peak_rss_kib', max),
                'generator_saturated_rounds': round_stat(rounds, 'generator_saturated', sum),
                'upstream_saturated_rounds': round_stat(rounds, 'upstream_saturated', sum),
            })
    return names, rows


def step_coordinates(xs, values, terminal=None):
    """Draw the retained release to the next known tag, breaking at every ungraded tag."""
    points = []
    for i, (x, y) in enumerate(zip(xs, values, strict=True)):
        if x is None or y is None:
            points.append((math.nan, math.nan))
            continue
        end = xs[i + 1] if i + 1 < len(xs) else terminal
        if end is not None and end < x:
            raise ValueError('release positions disagree with recorded order or terminal position')
        points.append((x, y))
        if end is not None:
            points.append((end, y))
    return points


def axis_definitions(data):
    releases = data['releases']
    elapsed = [(number(row['elapsed_seconds']) / 60 if row.get('elapsed_seconds') is not None else None)
               for row in releases]
    spend = [number((row.get('capacity') or {}).get('spent_usd_upper_bound')) for row in releases]
    started, ended = data.get('started_unix'), data.get('ended_unix')
    end_minutes = number(ended - started) / 60 if started is not None and ended is not None else None
    capacity = data.get('terminal_capacity') or {}
    return [('Elapsed builder time (min)', elapsed, end_minutes),
            ('Cumulative settled spend (USD, upper bound)', spend, number(capacity.get('spent_usd_upper_bound')))]


def mark_axis(ax, axis, show_xlabel=True):
    label, xs, end = axis
    recorded = [x for x in xs if x is not None]
    if end is not None:
        recorded.append(end)
        ax.axvline(end, color='#3b4650', ls=':', lw=1.2)
    if xs and xs[0] is not None and xs[0] > 0:
        ax.axvspan(0, xs[0], color='#e9edf0', zorder=-2)
    limit = max(recorded, default=0)
    ax.set_xlim(0, limit * 1.045 if limit else 1)
    if not recorded:
        ax.set_xticks([])
        ax.text(.5, .5, 'No recorded positions', transform=ax.transAxes, ha='center', va='center')
    if show_xlabel:
        ax.set_xlabel(label)
    ax.grid(axis='both', color='#e0e5e8', lw=.6)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)


def draw_series(ax, xs, values, terminal, color, marker='o', label=None):
    points = step_coordinates(xs, values, terminal)
    if points:
        ax.plot(*zip(*points), color=color, lw=1.4)
    positioned = [(x, y) for x, y in zip(xs, values, strict=True) if x is not None and y is not None]
    if positioned:
        ax.scatter(*zip(*positioned), color=color, marker=marker, s=30, edgecolors='white',
                   linewidths=.45, zorder=3, label=label)


def terminal_caption(data):
    capacity = data.get('terminal_capacity') or {}
    spend = number(capacity.get('spent_usd_upper_bound'))
    holds = number(capacity.get('reserved_usd'))
    parts = []
    if spend is not None:
        parts.append(f'${spend:.4f} settled')
    if holds is not None:
        parts.append(f'${holds:.4f} in unresolved holds')
    end = '  ·  '.join(parts) if parts else 'Terminal accounting unavailable'
    return f'{end}. Gray area precedes the first tag. Dotted line marks the recorded run end.'


def workload_label(name):
    pieces = name.rsplit('-', 2)
    if len(pieces) == 3 and pieces[1].isdigit() and pieces[2].isdigit():
        mode, size, clients = pieces
        return f'{mode} · {int(size) / 1024:g} KiB · {int(clients):,} clients'
    return name


def save(fig, directory, name):
    from matplotlib import pyplot as plt
    for extension in ('png', 'svg'):
        fig.savefig(directory / f'{name}.{extension}', dpi=160, bbox_inches='tight')
    plt.close(fig)


def plot(directory, output=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    directory = Path(directory)
    output = Path(output) if output is not None else directory
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads((directory / 'timeline.json').read_text())
    releases = data['releases']
    names, records = observations(data, declared_workloads(data))
    axes = axis_definitions(data)
    with (output / 'metrics.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    title = f"Stage {stage_number(data)}"
    if data.get('label'):
        title += '  ·  ' + data['label']
    fig, panels = plt.subplots(1, 2, figsize=(12, 3.9), sharey=True, layout='constrained')
    counts = [r.get('passed') for r in releases]
    total = data['total_checks']
    for ax, axis in zip(panels, axes, strict=True):
        _, xs, terminal = axis
        mark_axis(ax, axis)
        draw_series(ax, xs, counts, terminal, '#006c66')
        ax.set_ylim(-.6, max(total, max((v for v in counts if v is not None), default=0)) + 1.5)
        for x, count, row in zip(xs, counts, releases, strict=True):
            if x is None:
                continue
            tag = '#' + str(int(row['tag'].split('/')[-1]))
            if count is None:
                ax.plot(x, .035, transform=ax.get_xaxis_transform(), marker='x', color='#677580')
                if len(releases) <= 12:
                    ax.annotate(tag, (x, .035), xycoords=ax.get_xaxis_transform(), xytext=(3, 5),
                                textcoords='offset points', fontsize=8, color='#50616a')
            elif len(releases) <= 12:
                ax.annotate(tag, (x, count), xytext=(2, 7), textcoords='offset points', fontsize=8)
    panels[0].set_ylabel(f'Independent API checks passed (of {total})')
    fig.suptitle(title + '  |  Tagged API progress', fontweight='bold')
    note = terminal_caption(data)
    if any(count is None for count in counts):
        note += ' × marks tags without an API count.'
    if not releases:
        note += ' No tagged submission.'
    fig.supxlabel(note, fontsize=9, parse_math=False)
    save(fig, output, 'correctness')

    groups = {name: [] for name in names}
    for row in records:
        groups[row['workload']].append(row)
    qualified = [name for name in names if any(r['qualification'] == 'Qualified' for r in groups[name])]
    plotted_metrics = METRICS if qualified else ()
    status_height = max(1.4, len(names) * .28)
    heights = [1.8] * len(plotted_metrics) + [status_height]
    fig, panels = plt.subplots(len(heights), 2, figsize=(14, sum(heights) + 2.0),
                               squeeze=False, sharex='col', sharey='row', layout='constrained',
                               gridspec_kw={'height_ratios': heights})
    colors = plt.get_cmap('tab20')
    for i, (metric, ylabel) in enumerate(plotted_metrics):
        panels[i, 0].set_ylabel(ylabel)
        for col, axis in enumerate(axes):
            ax = panels[i, col]
            mark_axis(ax, axis, show_xlabel=False)
            for j, name in enumerate(qualified):
                values = [r[metric] for r in groups[name]]
                draw_series(ax, axis[1], values, axis[2], colors(j % colors.N), label=workload_label(name))
            if i == 0 and col == 0:
                handles, labels = ax.get_legend_handles_labels()
                if labels:
                    ax.legend(handles, labels, fontsize=7, loc='best', ncols=max(1, len(labels) // 10 + 1))
    present = {r['qualification'] for r in records}
    for col, axis in enumerate(axes):
        ax = panels[-1, col]
        mark_axis(ax, axis)
        ax.set_yticks(range(len(names)), labels=[workload_label(n) for n in names], fontsize=8)
        ax.set_ylim(max(len(names) - .45, .55), -.55)
        for i, name in enumerate(names):
            for x, row in zip(axis[1], groups[name], strict=True):
                if x is not None:
                    ax.scatter(x, i, marker='s', s=42, color=STATUS_COLORS[row['qualification']],
                               edgecolors='white', linewidths=.4, zorder=3)
        if not releases:
            ax.set_title('No tagged submission')
    panels[-1, 0].set_ylabel('Workload at each tag')
    if present:
        legend = [Line2D([], [], marker='s', ls='', color=color, label=status, markersize=6)
                  for status, color in STATUS_COLORS.items() if status in present]
        panels[-1, 0].legend(handles=legend, loc='upper left', bbox_to_anchor=(0, -.34),
                              ncols=min(4, len(legend)), frameon=False, fontsize=8)
    heading = 'Qualified performance by release' if qualified else 'No qualifying performance measurements'
    fig.suptitle(title + '  |  ' + heading, fontweight='bold')
    fig.supxlabel(terminal_caption(data), fontsize=9, parse_math=False)
    save(fig, output, 'performance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Directory containing timeline.json')
    parser.add_argument('--output', type=Path, help='Destination for figures and metrics.csv')
    args = parser.parse_args()
    plot(args.directory, args.output)
