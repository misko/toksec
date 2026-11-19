# Stage 5: level-5-a4ba853a82fe

Model: gpt-6.1-terra; finished: True; retained: fdb0544f86ab45739c765044041e2563
Calls: 17; tokens: 507426; cost upper bound: $0.25732560

| Candidate | Passed checks | Build | Retained |
|---|---:|---|---|
| fdb0544f86ab | 4/4 | True | True |
| 1fcee744a981 | 4/4 | True | False |

| Measurement | Candidate | Workload | Median req/s | Worst p99 ms | Failures | Eligible | Promoted |
|---|---|---|---:|---:|---:|---|---|
| 1 | fdb0544f86ab | cache-hit-4096-256 | 104038.0 | 19.1 | 0 | False | False |
| 2 | fdb0544f86ab | persistent-65536-4096 | 10655.0 | 912.2 | 0 | False | False |
| 3 | 1fcee744a981 | persistent-65536-4096 | 26631.3 | 1109.6 | 532 | False | False |
| 3 | fdb0544f86ab | persistent-65536-4096 | 10786.0 | 1606.0 | 560 | False | False |
| 4 | 1fcee744a981 | persistent-65536-256 | 22421.0 | 201.6 | 0 | False | False |
| 4 | fdb0544f86ab | persistent-65536-256 | 13353.3 | 478.0 | 220 | False | False |
| 5 | 1fcee744a981 | cache-hit-4096-256 | 67435.7 | 40.5 | 0 | False | False |
| 5 | 1fcee744a981 | cache-hit-4096-4096 | 37365.7 | 788.1 | 826 | False | False |
| 5 | 1fcee744a981 | cache-hit-65536-256 | 13473.3 | 158.1 | 0 | False | False |
| 5 | 1fcee744a981 | cache-hit-65536-4096 | 3382.0 | None | 196939 | False | False |
| 5 | 1fcee744a981 | cache-miss-4096-256 | 19825.7 | 116.4 | 0 | False | False |
| 5 | 1fcee744a981 | cache-miss-4096-4096 | 7449.3 | 1658.6 | 16392 | False | False |
| 5 | 1fcee744a981 | cache-miss-65536-256 | 5671.3 | 234.6 | 7 | False | False |
| 5 | 1fcee744a981 | cache-miss-65536-4096 | 537.3 | None | 479074 | False | False |
| 5 | 1fcee744a981 | fresh-4096-256 | 15901.7 | 180.7 | 44 | False | False |
| 5 | 1fcee744a981 | fresh-4096-4096 | 9759.7 | 1476.0 | 0 | False | False |
| 5 | 1fcee744a981 | fresh-65536-256 | 11157.7 | 237.0 | 0 | False | False |
| 5 | 1fcee744a981 | fresh-65536-4096 | 9694.0 | 1712.9 | 0 | False | False |
| 5 | 1fcee744a981 | persistent-4096-256 | 5170.7 | 227.3 | 0 | False | False |
| 5 | 1fcee744a981 | persistent-4096-4096 | 28989.3 | 797.7 | 0 | False | False |
| 5 | 1fcee744a981 | persistent-65536-256 | 19234.0 | 260.2 | 0 | False | False |
| 5 | 1fcee744a981 | persistent-65536-4096 | 22205.3 | 2000.1 | 1360 | False | False |
| 5 | 1fcee744a981 | proxy-4096-256 | 20122.0 | 985.0 | 182 | False | False |
| 5 | 1fcee744a981 | proxy-4096-4096 | 7667.7 | 1929.1 | 16617 | False | False |
| 5 | 1fcee744a981 | proxy-65536-256 | 6565.0 | 687.9 | 0 | False | False |
| 5 | 1fcee744a981 | proxy-65536-4096 | 0.0 | None | 379581 | False | False |
| 5 | 1fcee744a981 | routed-4096-256 | 5820.3 | 157.6 | 0 | False | False |
| 5 | 1fcee744a981 | routed-4096-4096 | 29974.7 | 1109.0 | 0 | False | False |
| 5 | 1fcee744a981 | routed-65536-256 | 38316.0 | 227.4 | 64 | False | False |
| 5 | 1fcee744a981 | routed-65536-4096 | 27335.0 | 1425.5 | 0 | False | False |
| 5 | fdb0544f86ab | cache-hit-4096-256 | 70287.3 | 81.5 | 0 | False | False |
| 5 | fdb0544f86ab | cache-hit-4096-4096 | 35122.3 | 621.0 | 0 | False | False |
| 5 | fdb0544f86ab | cache-hit-65536-256 | 12718.0 | 240.1 | 0 | False | False |
| 5 | fdb0544f86ab | cache-hit-65536-4096 | 8685.0 | None | 196742 | False | False |
| 5 | fdb0544f86ab | cache-miss-4096-256 | 19889.3 | 78.7 | 0 | False | False |
| 5 | fdb0544f86ab | cache-miss-4096-4096 | 7149.3 | 1899.1 | 17356 | False | False |
| 5 | fdb0544f86ab | cache-miss-65536-256 | 6223.0 | 243.5 | 0 | False | False |
| 5 | fdb0544f86ab | cache-miss-65536-4096 | 89.3 | None | 422327 | False | False |
| 5 | fdb0544f86ab | fresh-4096-256 | 18566.0 | 210.8 | 0 | False | False |
| 5 | fdb0544f86ab | fresh-4096-4096 | 10436.3 | 1293.8 | 58 | False | False |
| 5 | fdb0544f86ab | fresh-65536-256 | 6139.0 | 804.2 | 0 | False | False |
| 5 | fdb0544f86ab | fresh-65536-4096 | 7005.7 | 2000.1 | 1720 | False | False |
| 5 | fdb0544f86ab | persistent-4096-256 | 49200.7 | 63.9 | 0 | False | False |
| 5 | fdb0544f86ab | persistent-4096-4096 | 39338.0 | 252.0 | 0 | False | False |
| 5 | fdb0544f86ab | persistent-65536-256 | 11180.3 | 285.1 | 0 | False | False |
| 5 | fdb0544f86ab | persistent-65536-4096 | 10684.0 | 1799.3 | 960 | False | False |
| 5 | fdb0544f86ab | proxy-4096-256 | 21495.0 | 54.8 | 0 | True | False |
| 5 | fdb0544f86ab | proxy-4096-4096 | 7666.0 | 1410.6 | 13674 | False | False |
| 5 | fdb0544f86ab | proxy-65536-256 | 5735.3 | 849.7 | 0 | False | False |
| 5 | fdb0544f86ab | proxy-65536-4096 | 0.0 | None | 433878 | False | False |
| 5 | fdb0544f86ab | routed-4096-256 | 68430.0 | 30.2 | 0 | False | False |
| 5 | fdb0544f86ab | routed-4096-4096 | 39392.3 | 604.5 | 0 | False | False |
| 5 | fdb0544f86ab | routed-65536-256 | 13946.7 | 667.1 | 0 | False | False |
| 5 | fdb0544f86ab | routed-65536-4096 | 12836.7 | 712.9 | 0 | False | False |

Measurement 1: selected workload diagnostic; full matrix required for baseline promotion
Measurement 2: selected workload diagnostic; full matrix required for baseline promotion
Measurement 3: selected workload diagnostic; full matrix required for baseline promotion
Measurement 4: selected workload diagnostic; full matrix required for baseline promotion
Measurement 5: generator or environment inconclusive

Graded release: release/000002 at 601f1d6113bfe3142d04e3de7ed011bc535e42cf

Ineligible measurements do not establish a performance improvement. Full round metrics are preserved in benchmarks/*.json.