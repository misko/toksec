"""Identified calibration evidence, separate from submitted-server results."""
from datetime import datetime, timezone
import hashlib
import uuid
from pathlib import Path

from toksec.storage import atomic_json
from toksec.result_storage import read


def identity(commit):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'calibration__static-http__{stamp}__{commit[:12]}__{uuid.uuid4().hex[:8]}'


def index(root):
    root = Path(root)
    records = []
    for path in sorted(root.glob('*/calibration.json')):
        record = read(path)
        meta = read(path.parent / 'record.json') if (path.parent / 'record.json').exists() else record
        records.append({'calibration_id': meta['calibration_id'], 'path': path.parent.name,
                        'toksec_commit': meta.get('toksec_commit'),
                        'static_generator_ready': record.get('static_generator_ready', False),
                        'applicability': 'Explicit workload and environment match required; never inferred from recency'})
    atomic_json(root / 'index.json', {'calibrations': records})
    (root / 'README.md').write_text('# Benchmark calibrations\n\nThese records assess the measurement machinery, not agent implementations.\n'
        'A record applies only to matching workloads, probe, environment and resource limits.\n\n' +
        '\n'.join(f'- [{r["calibration_id"]}]({r["path"]}/report.md)' for r in records) + '\n')
    return records
