"""Current Stage 10 packet assembled from shared policy and stage requirements."""
from decimal import Decimal
import json
from pathlib import Path

from toksec.artifacts import artifact_contract

ROOT = Path(__file__).resolve().parents[2]
STAGE = Path(__file__).resolve().parent


def input_files(language):
    artifact_contract(10, language)
    files = {
        'builder/RULES.md': ROOT / 'RULES.md',
        'builder/ARTIFACTS.md': ROOT / 'stages/common/ARTIFACTS.md',
    }
    for name in ('START', 'INTERFACE'):
        files[f'builder/{name}.md'] = STAGE / 'builder' / (name + '.md')
    files[f'builder/languages/{language}.md'] = STAGE / 'builder/languages' / (language + '.md')
    for name in ('HTTP', 'CONFIGURATION', 'TLS', 'OPERATIONS', 'BENCHMARK', 'SMOKE'):
        files[f'builder/{name}.md'] = STAGE / 'builder' / (name + '.md')
    return files


def packet(language='cpp', budget='2.00'):
    amount = Decimal(str(budget))
    if not amount.is_finite() or amount <= 0 or amount > 2:
        raise ValueError('Stage 10 request-budget profile requires a positive cap of at most $2')
    sections = ['# Stage 10 implementation assignment', '']
    sections.extend(path.read_text() for path in input_files(language).values())
    sections.append(f'''Operational campaign notice, authoritative over draft availability statements:
The shared RULES.md above is the current policy. This stage has sandboxed
compilation, standalone tests and ordinary smoke feedback. Independent API
coverage is partial, and performance measurements are provisional diagnostics.
Neither passing the available API checks nor a diagnostic establishes full-stage
acceptance or final performance credit. The full acceptance suite and calibrated
performance matrix remain incomplete.

Implement the server, configuration, HTTP parsing, workers and TLS integration
yourself. OpenSSL headers/libraries are supplied, not server code. The controller
reports a strict ${format(amount, 'f')} model-spend cap for this run; any enclosing
campaign ledger also limits admission. Standard service tier and medium reasoning
are used. Requests are counted before admission. Reasoning and text share the
enforced output limit, so prefer complete bounded improvements.

Your full latest source and notes are retained outside request context. read_source
retrieves omitted source. run_tests compiles a standalone test executable; it
starts no candidate automatically. read_input accepts artifact.json, packet-relative
builder/ or fixtures/ paths, and approved OpenSSL headers under openssl/.
Certificate private keys are public test fixtures. Read capacity for effective
sandbox task and descriptor limits. Per-process limits enforce the total descriptor
bound across the bounded process tree.
''')
    sections.extend(['## Artifact contract', '', '```json',
                     json.dumps(artifact_contract(10, language), indent=2, sort_keys=True), '```', ''])
    return '\n\n'.join(sections)
