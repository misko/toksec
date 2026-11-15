# Stage 1: level-1-0989d5c40297

Model: gpt-6.1-terra; finished: True; retained: 2c58c533b4e8465c80f912d82279d39a
Calls: 24; tokens: 584813; cost upper bound: $0.25617370

| Candidate | Passed checks | Build | Retained |
|---|---:|---|---|
| 2c58c533b4e8 | 1/1 | True | True |
| 21a06dd1e11c | 1/1 | True | False |
| e0f186b2c32c | 1/1 | True | False |

| Measurement | Candidate | Workload | Median req/s | Worst p99 ms | Failures | Eligible | Promoted |
|---|---|---|---:|---:|---:|---|---|
| 1 | 2c58c533b4e8 | fresh-4096-256 | 25081.7 | 149.5 | 0 | False | False |
| 1 | 2c58c533b4e8 | fresh-4096-4096 | 13427.7 | 1300.1 | 374 | False | False |
| 1 | 2c58c533b4e8 | fresh-65536-256 | 14946.3 | 149.6 | 0 | False | False |
| 1 | 2c58c533b4e8 | fresh-65536-4096 | 8068.3 | 1369.0 | 2856 | False | False |
| 2 | 21a06dd1e11c | fresh-4096-256 | 35286.7 | 49.2 | 0 | False | False |
| 2 | 21a06dd1e11c | fresh-4096-4096 | 12638.0 | 1033.1 | 721 | False | False |
| 2 | 21a06dd1e11c | fresh-65536-256 | 13109.7 | 203.7 | 0 | False | False |
| 2 | 21a06dd1e11c | fresh-65536-4096 | 9704.7 | 965.8 | 1579 | False | False |
| 2 | 2c58c533b4e8 | fresh-4096-256 | 36629.3 | 67.7 | 0 | False | False |
| 2 | 2c58c533b4e8 | fresh-4096-4096 | 14298.3 | 1237.3 | 0 | False | False |
| 2 | 2c58c533b4e8 | fresh-65536-256 | 10291.0 | 117.3 | 0 | False | False |
| 2 | 2c58c533b4e8 | fresh-65536-4096 | 9453.0 | 1099.1 | 1851 | False | False |
| 3 | 2c58c533b4e8 | fresh-4096-256 | 32417.3 | 26.0 | 0 | False | False |
| 3 | 2c58c533b4e8 | fresh-4096-4096 | 14373.7 | 1119.7 | 159 | False | False |
| 3 | 2c58c533b4e8 | fresh-65536-256 | 17167.0 | 52.5 | 0 | False | False |
| 3 | 2c58c533b4e8 | fresh-65536-4096 | 11108.3 | 1036.4 | 148 | False | False |
| 3 | e0f186b2c32c | fresh-4096-256 | 25040.7 | 42.6 | 0 | False | False |
| 3 | e0f186b2c32c | fresh-4096-4096 | 11648.3 | 1108.9 | 174 | False | False |
| 3 | e0f186b2c32c | fresh-65536-256 | 15789.7 | 56.1 | 0 | False | False |
| 3 | e0f186b2c32c | fresh-65536-4096 | 11719.7 | 663.2 | 662 | False | False |

Measurement 1: initial accepted baseline
Measurement 2: generator or environment inconclusive
Measurement 3: generator or environment inconclusive

Graded release: release/000003 at bfbe4984ce3c47cd60480467326a5be13cc0581c

Ineligible measurements do not establish a performance improvement. Full round metrics are preserved in benchmarks/*.json.