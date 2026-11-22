# Stage 14 gateway calibration

Calibration ID `calibration__stage-14__20261120T152615Z__6c35c0f9f68b__a87edff6`

| Workload | Qualified | A/A variation | Control gain | Reasons |
|---|---|---:|---:|---|
| gateway-14-admitted-4096-256 | True | 2.1% | 272.5% |  |
| gateway-14-admitted-4096-4096 | False | 9.5% | 208.5% | reference_repeat_variation |
| gateway-14-public-4096-256 | False | 1.0% | 0.5% | known_slow_control_indistinguishable |
| gateway-14-public-65536-256 | False | 4.5% | 349.8% | generator:insufficient_headroom |
| gateway-14-admitted-65536-256 | False | 5.9% | 125.5% | reference_repeat_variation |
| gateway-14-public-4096-4096 | True | 3.0% | 259.9% |  |
| gateway-14-public-65536-4096 | False | 1.9% | 328.8% | generator:insufficient_headroom |
| gateway-14-admitted-65536-4096 | False | unavailable | unavailable | reference:effects_unverified, reference:no_valid_delivery, reference:request_failures, repeat:effects_unverified, repeat:no_valid_delivery, repeat:request_failures, slow_control:effects_unverified, slow_control:no_valid_delivery, slow_control:request_failures, reference_repeat_variation, known_slow_control_indistinguishable |

Status `completed`. See calibration.json for raw rounds, source identity and host configuration.
