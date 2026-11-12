# Luna Level 1 pilot

Luna produced a static HTTP server that passes all 41 checks in the six development groups. It submitted four candidates in 11 model requests and finished voluntarily. The accepted source is `server.py`; its exact checks are in `report.json`.

The run used 132,981 total tokens: 120,662 input and 12,319 output. Cached input accounts for 97,533 of the input tokens; reasoning accounts for 4,713 of the output tokens. The published-rate cost upper bound is $0.01291213. No reservations remain unresolved. Setup and local compute are excluded.

This is a pilot with an operator recovery, not a clean benchmark. The first response exposed a 78-token discrepancy between preflight counting and reported input usage. The controller stopped before dispatch. After correcting reservations, we reconciled the response within its original allowance and continued with fresh model context. All calls share the original $5 cap, 10,000,000-token cap, and deadline. Elapsed time including recovery was about 233 seconds.

`ledger.json` contains every request reservation and settled usage record. `summary.json` records aggregate counts, provenance, and the recovery. The first record retains its original preflight bound for audit; settlement verifies its actual total and cost fit the original reservation. Later records reserve the model-wide input ceiling.

The promotion suite is adaptive and visible through evaluation reports. There is no sealed final test or exploit assessment. Passing these checks does not establish general HTTP conformance or security. The recorded performance sample is exploratory local throughput, not a controlled benchmark.
