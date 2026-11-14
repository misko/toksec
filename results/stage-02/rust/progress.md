# Stage 2: level-2-5327b2715c64

Model: gpt-6.1-terra; finished: True; retained: 84dfd49fe90a4d47baaf3d959322b622
Calls: 21; tokens: 598464; cost upper bound: $0.25696980

| Candidate | Passed checks | Build | Retained |
|---|---:|---|---|
| 84dfd49fe90a | 3/3 | True | True |
| 344463975260 | 3/3 | True | False |
| 0a6268a99ecc | 3/3 | True | False |

| Measurement | Candidate | Workload | Median req/s | Worst p99 ms | Failures | Eligible | Promoted |
|---|---|---|---:|---:|---:|---|---|
| 1 | 344463975260 | fresh-4096-256 | 29528.0 | 56.5 | 0 | False | False |
| 1 | 344463975260 | fresh-4096-4096 | 18586.7 | 1681.3 | 4006 | False | False |
| 1 | 344463975260 | fresh-65536-256 | 19580.7 | 113.9 | 0 | False | False |
| 1 | 344463975260 | fresh-65536-4096 | 9620.7 | 1538.0 | 3044 | False | False |
| 1 | 344463975260 | persistent-4096-256 | 124133.3 | 16.1 | 0 | False | False |
| 1 | 344463975260 | persistent-4096-4096 | 59469.3 | 532.1 | 0 | False | False |
| 1 | 344463975260 | persistent-65536-256 | 25482.0 | 727.2 | 0 | False | False |
| 1 | 344463975260 | persistent-65536-4096 | 27757.0 | 542.1 | 0 | False | False |
| 1 | 84dfd49fe90a | fresh-4096-256 | 34748.3 | 36.2 | 0 | False | False |
| 1 | 84dfd49fe90a | fresh-4096-4096 | 17903.7 | 1325.7 | 3481 | False | False |
| 1 | 84dfd49fe90a | fresh-65536-256 | 17566.3 | 41.5 | 0 | False | False |
| 1 | 84dfd49fe90a | fresh-65536-4096 | 12466.3 | 1674.0 | 3039 | False | False |
| 1 | 84dfd49fe90a | persistent-4096-256 | 93531.0 | 17.8 | 0 | False | False |
| 1 | 84dfd49fe90a | persistent-4096-4096 | 64599.7 | 599.0 | 0 | False | False |
| 1 | 84dfd49fe90a | persistent-65536-256 | 30588.7 | 36.8 | 1 | False | False |
| 1 | 84dfd49fe90a | persistent-65536-4096 | 25879.0 | 1229.5 | 0 | False | False |
| 2 | 0a6268a99ecc | fresh-4096-256 | 23088.0 | 742.9 | 0 | False | False |
| 2 | 0a6268a99ecc | fresh-4096-4096 | 14071.7 | 1716.1 | 0 | False | False |
| 2 | 0a6268a99ecc | fresh-65536-256 | 13313.7 | 196.0 | 0 | False | False |
| 2 | 0a6268a99ecc | fresh-65536-4096 | 12903.0 | 1892.2 | 2911 | False | False |
| 2 | 0a6268a99ecc | persistent-4096-256 | 63302.3 | 19.9 | 0 | False | False |
| 2 | 0a6268a99ecc | persistent-4096-4096 | 61352.0 | 557.2 | 0 | False | False |
| 2 | 0a6268a99ecc | persistent-65536-256 | 32541.3 | 226.5 | 0 | False | False |
| 2 | 0a6268a99ecc | persistent-65536-4096 | 19190.0 | 1630.3 | 125 | False | False |
| 2 | 84dfd49fe90a | fresh-4096-256 | 29407.7 | 1156.3 | 0 | False | False |
| 2 | 84dfd49fe90a | fresh-4096-4096 | 14622.7 | 1967.4 | 1330 | False | False |
| 2 | 84dfd49fe90a | fresh-65536-256 | 16666.7 | 83.0 | 29 | False | False |
| 2 | 84dfd49fe90a | fresh-65536-4096 | 11687.7 | 1498.0 | 4131 | False | False |
| 2 | 84dfd49fe90a | persistent-4096-256 | 35479.3 | 21.6 | 0 | False | False |
| 2 | 84dfd49fe90a | persistent-4096-4096 | 51017.7 | 418.4 | 0 | False | False |
| 2 | 84dfd49fe90a | persistent-65536-256 | 27241.7 | 30.6 | 0 | False | False |
| 2 | 84dfd49fe90a | persistent-65536-4096 | 21699.7 | 2000.1 | 82 | False | False |

Measurement 1: generator or environment inconclusive
Measurement 2: generator or environment inconclusive

Graded release: release/000003 at cbf69fb59032204d7bf6077d8a230ca7df879505

Ineligible measurements do not establish a performance improvement. Full round metrics are preserved in benchmarks/*.json.