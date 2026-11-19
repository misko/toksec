# Stage 2: level-2-1d7d52f32031

Model: gpt-6.1-terra; finished: True; retained: 8f1593fc886e4ca1b6abebfdc226055c
Calls: 18; tokens: 496941; cost upper bound: $0.25513815

| Candidate | Passed checks | Build | Retained |
|---|---:|---|---|
| 8f1593fc886e | 3/3 | True | True |
| b5309ab0dfbc | 3/3 | True | False |
| eabc255bc33d | 3/3 | True | False |

| Measurement | Candidate | Workload | Median req/s | Worst p99 ms | Failures | Eligible | Promoted |
|---|---|---|---:|---:|---:|---|---|
| 1 | 8f1593fc886e | fresh-4096-256 | 27972.7 | 51.5 | 0 | False | False |
| 1 | 8f1593fc886e | fresh-4096-4096 | 17308.7 | 1068.3 | 0 | False | False |
| 1 | 8f1593fc886e | fresh-65536-256 | 16181.7 | 43.7 | 0 | False | False |
| 1 | 8f1593fc886e | fresh-65536-4096 | 12019.3 | 749.3 | 0 | False | False |
| 1 | 8f1593fc886e | persistent-4096-256 | 61806.7 | 24.6 | 0 | False | False |
| 1 | 8f1593fc886e | persistent-4096-4096 | 73225.7 | 573.1 | 0 | False | False |
| 1 | 8f1593fc886e | persistent-65536-256 | 34383.0 | 21.3 | 0 | False | False |
| 1 | 8f1593fc886e | persistent-65536-4096 | 26395.0 | 2000.1 | 0 | False | False |
| 2 | 8f1593fc886e | fresh-4096-256 | 30703.3 | 119.2 | 0 | False | False |
| 2 | 8f1593fc886e | fresh-4096-4096 | 15354.0 | 2000.1 | 0 | False | False |
| 2 | 8f1593fc886e | fresh-65536-256 | 16848.0 | 56.6 | 0 | False | False |
| 2 | 8f1593fc886e | fresh-65536-4096 | 12285.3 | 741.8 | 0 | False | False |
| 2 | 8f1593fc886e | persistent-4096-256 | 135523.3 | 11.1 | 0 | False | False |
| 2 | 8f1593fc886e | persistent-4096-4096 | 79680.0 | 306.9 | 0 | False | False |
| 2 | 8f1593fc886e | persistent-65536-256 | 33204.3 | 24.0 | 0 | False | False |
| 2 | 8f1593fc886e | persistent-65536-4096 | 24178.3 | 458.3 | 0 | False | False |
| 2 | b5309ab0dfbc | fresh-4096-256 | 29295.7 | 120.2 | 0 | False | False |
| 2 | b5309ab0dfbc | fresh-4096-4096 | 15810.7 | 562.3 | 0 | False | False |
| 2 | b5309ab0dfbc | fresh-65536-256 | 16408.3 | 99.1 | 0 | False | False |
| 2 | b5309ab0dfbc | fresh-65536-4096 | 13173.3 | 780.7 | 0 | False | False |
| 2 | b5309ab0dfbc | persistent-4096-256 | 103259.0 | 395.1 | 0 | False | False |
| 2 | b5309ab0dfbc | persistent-4096-4096 | 75388.0 | 164.8 | 0 | False | False |
| 2 | b5309ab0dfbc | persistent-65536-256 | 34383.3 | 25.2 | 0 | False | False |
| 2 | b5309ab0dfbc | persistent-65536-4096 | 22957.3 | 752.0 | 0 | False | False |
| 3 | 8f1593fc886e | fresh-4096-256 | 30439.7 | 35.7 | 0 | False | False |
| 3 | 8f1593fc886e | fresh-4096-4096 | 13067.0 | 1193.4 | 0 | False | False |
| 3 | 8f1593fc886e | fresh-65536-256 | 15755.7 | 55.0 | 0 | False | False |
| 3 | 8f1593fc886e | fresh-65536-4096 | 9184.7 | 1194.2 | 0 | False | False |
| 3 | 8f1593fc886e | persistent-4096-256 | 121264.7 | 21.2 | 0 | False | False |
| 3 | 8f1593fc886e | persistent-4096-4096 | 72002.0 | 235.6 | 0 | False | False |
| 3 | 8f1593fc886e | persistent-65536-256 | 28985.7 | 31.0 | 0 | False | False |
| 3 | 8f1593fc886e | persistent-65536-4096 | 26007.0 | 293.3 | 0 | False | False |
| 3 | eabc255bc33d | fresh-4096-256 | 30755.7 | 245.6 | 0 | False | False |
| 3 | eabc255bc33d | fresh-4096-4096 | 10219.7 | 779.5 | 0 | False | False |
| 3 | eabc255bc33d | fresh-65536-256 | 16735.7 | 83.4 | 0 | False | False |
| 3 | eabc255bc33d | fresh-65536-4096 | 7835.3 | 1034.9 | 0 | False | False |
| 3 | eabc255bc33d | persistent-4096-256 | 145132.3 | 16.0 | 0 | False | False |
| 3 | eabc255bc33d | persistent-4096-4096 | 69657.0 | 291.0 | 0 | False | False |
| 3 | eabc255bc33d | persistent-65536-256 | 26630.3 | 50.9 | 0 | False | False |
| 3 | eabc255bc33d | persistent-65536-4096 | 25362.0 | 310.3 | 0 | False | False |

Measurement 1: initial accepted baseline
Measurement 2: generator or environment inconclusive
Measurement 3: generator or environment inconclusive

Graded release: release/000003 at a78115cd02bf7a5c4f8dc5d5eb211a25b1187d94

Ineligible measurements do not establish a performance improvement. Full round metrics are preserved in benchmarks/*.json.