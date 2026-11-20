"""Identified calibration evidence, separate from submitted-server results."""
from datetime import datetime, timezone
import hashlib
import json
import uuid
from pathlib import Path

from toksec.storage import atomic_json
from toksec.result_storage import read


def identity(commit):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'calibration__static-http__{stamp}__{commit[:12]}__{uuid.uuid4().hex[:8]}'


def gateway_receipt(path, stage, workloads):
    """Validate the host-owned receipt against the current measurement environment."""
    from toksec.gateway_calibration import environment, measurement_fingerprint

    raw = Path(path).read_bytes()
    record = json.loads(raw)
    if not isinstance(record, dict) or stage not in (14, 16):
        raise ValueError('gateway calibration requires a Stage 14 or Stage 16 receipt')
    expected = {w['id']: w for w in workloads}
    observed = record.get('workloads')
    cells = record.get('cells')
    if (not isinstance(record.get('calibration_id'), str) or not record['calibration_id']
            or record.get('status') != 'completed' or record.get('stage') != stage
            or not isinstance(observed, dict) or not observed
            or not isinstance(cells, dict) or cells.keys() != observed.keys()
            or any(not isinstance(cell, dict) or type(cell.get('qualified')) is not bool
                   or not isinstance(cell.get('reasons'), list) for cell in cells.values())
            or any(key not in expected or expected[key] != value for key, value in observed.items())
            or record.get('measurement_fingerprint') != measurement_fingerprint(stage)
            or record.get('environment') != environment()):
        raise ValueError('calibration does not match stage, workload definitions or host CPU affinity')
    return record, hashlib.sha256(raw).hexdigest()


def environment_digest(environment):
    data = json.dumps(environment, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(data).hexdigest()


def development_hint(path, stage, workloads):
    record, digest = gateway_receipt(path, stage, workloads)
    name = record.get('diagnostic_workload')
    cell = record['cells'].get(name) if isinstance(name, str) else None
    if (not cell or not cell['qualified'] or cell['reasons'] or record.get('diagnostic_ready') is not True
            or record.get('declared_rounds') != record['workloads'][name]['rounds']):
        raise ValueError('the named diagnostic workload lacks a qualified full-round calibration')
    return {'id': record['calibration_id'], 'sha256': digest, 'workload': name,
            'measurement_fingerprint': record['measurement_fingerprint'],
            'environment_sha256': environment_digest(record['environment'])}


def index(root):
    root = Path(root)
    records = []
    for path in sorted(root.glob('*/calibration.json')):
        record = read(path)
        meta = read(path.parent / 'record.json') if (path.parent / 'record.json').exists() else record
        records.append({'calibration_id': meta['calibration_id'], 'path': path.parent.name,
                        'toksec_commit': meta.get('toksec_commit'),
                        'static_generator_ready': record.get('static_generator_ready', False),
                        **({key: record.get(key) for key in ('stage', 'diagnostic_ready', 'confirmation_ready', 'full_matrix_ready')}
                           if record.get('stage') in (14, 16) else {}),
                        'applicability': 'Explicit workload and environment match required; never inferred from recency'})
    atomic_json(root / 'index.json', {'calibrations': records})
    (root / 'README.md').write_text('# Benchmark calibrations\n\nThese records assess the measurement machinery, not agent implementations.\n'
        'A record applies only to matching workloads, probe, environment and resource limits.\n\n' +
        '\n'.join(f'- [{r["calibration_id"]}]({r["path"]}/report.md)' for r in records) + '\n')
    return records
