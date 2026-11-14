# Stage layout verification

The v5 contract keeps shared builder rules, process interface, HTTP behavior and
measurement definitions separate from Stage 1/2 contracts and workload registries.
The packet and runtime checker list select the same stage registry.

Verification performed without paid model calls:

- Regression coverage checks independent packets, no starter acceptance for either
  stage, saved instruction inputs, workload counts, and API-failure prevention of
  benchmark execution.
- The real evaluate.py CLI compiled the archived Luna Stage 2 source inside the
  sandbox and ran all 21 independent cases. It passed 20, including all three new
  configured-limit checks. Its pre-existing opaque-header-value behavior failed.
  Grading reported failed_api and zero performance credit.
- Two temporary mutations of that archived source validated negative cases.
  Replacing its connection limit with 10,000 failed connection-capacity because
  the excess client was served. Extending its write timeout to 10 seconds failed
  write-deadline because the occupied slot prevented the recovery request.
- Backpressure coverage verifies ordered responses and service to another client
  after a burst exceeds pipeline_depth. It does not prove an internal queue bound.

The archive was only validation input. No archived source is copied into a builder
packet or offered as a starter. Historical evaluators and results remain unchanged.

Final frozen-tree verification: `python3 -m unittest discover -s tests -v`
passed all 72 tests. `git diff --check` passed. Real CLI preparation confirmed a
$3 default ledger, Terra medium, a 7200-second ceiling and no starter metadata.
