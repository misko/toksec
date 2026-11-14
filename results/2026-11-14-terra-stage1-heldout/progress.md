# Stage 1: level-1-2afe956f08cb

Model: gpt-6.1-terra; finished: True; retained: f5aab1c33e9c4320aaf2185924f35928
Calls: 25; tokens: 722650; cost upper bound: $0.26525600

| Candidate | Passed checks | Build | Retained |
|---|---:|---|---|
| f5aab1c33e9c | 1/1 | True | True |
| 96d082197866 | 1/1 | True | False |
| aae761a595ef | 1/1 | True | False |

| Measurement | Candidate | Workload | Median req/s | Worst p99 ms | Failures | Eligible | Promoted |
|---|---|---|---:|---:|---:|---|---|
| 1 | f5aab1c33e9c | fresh-4096-256 | 23700.7 | 30.9 | 0 | False | False |
| 1 | f5aab1c33e9c | fresh-4096-4096 | 14224.0 | 538.3 | 0 | False | False |
| 1 | f5aab1c33e9c | fresh-65536-256 | 18904.3 | 42.5 | 0 | False | False |
| 1 | f5aab1c33e9c | fresh-65536-4096 | 14419.7 | 588.7 | 0 | False | False |
| 2 | 96d082197866 | fresh-4096-256 | 29590.3 | 22.6 | 20 | False | False |
| 2 | 96d082197866 | fresh-4096-4096 | 12299.7 | 2000.1 | 1070 | False | False |
| 2 | 96d082197866 | fresh-65536-256 | 16292.0 | 88.0 | 0 | False | False |
| 2 | 96d082197866 | fresh-65536-4096 | 6302.3 | 1882.4 | 6270 | False | False |
| 2 | f5aab1c33e9c | fresh-4096-256 | 29546.0 | 21.7 | 0 | False | False |
| 2 | f5aab1c33e9c | fresh-4096-4096 | 16024.0 | 1543.3 | 1376 | False | False |
| 2 | f5aab1c33e9c | fresh-65536-256 | 20198.0 | 73.5 | 0 | False | False |
| 2 | f5aab1c33e9c | fresh-65536-4096 | 8225.0 | 2000.1 | 265 | False | False |
| 3 | aae761a595ef | fresh-4096-256 | 26163.0 | 70.7 | 3 | False | False |
| 3 | aae761a595ef | fresh-4096-4096 | 15769.3 | 711.0 | 723 | False | False |
| 3 | aae761a595ef | fresh-65536-256 | 17925.7 | 65.2 | 0 | False | False |
| 3 | aae761a595ef | fresh-65536-4096 | 14085.3 | 821.5 | 0 | False | False |
| 3 | f5aab1c33e9c | fresh-4096-256 | 24490.3 | 119.8 | 0 | False | False |
| 3 | f5aab1c33e9c | fresh-4096-4096 | 12839.0 | 571.4 | 1024 | False | False |
| 3 | f5aab1c33e9c | fresh-65536-256 | 16224.0 | 61.3 | 0 | False | False |
| 3 | f5aab1c33e9c | fresh-65536-4096 | 13788.3 | 728.2 | 0 | False | False |

Measurement 1: initial accepted baseline
Measurement 2: generator or environment inconclusive
Measurement 3: generator or environment inconclusive

Graded release: release/000003 at 7a97bada5d432fa144e465aeee1832588e527337

Ineligible measurements do not establish a performance improvement. Full round metrics are preserved in benchmarks/*.json.