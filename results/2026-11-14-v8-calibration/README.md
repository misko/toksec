# v8 static load-generator calibration

Host-only calibration; no model calls. One round per workload is a diagnostic,
not a scored five-round comparison. Seven of eight workloads were ineligible.
Do not interpret raw throughput as validated performance.

The probe runs on CPU 16; four generators on CPUs 17–20. CPU 21 was available.
The separate regression suite used CPUs 10–15.

| Workload | Raw req/s | Failures | Eligible | Generator saturated |
|---|---:|---:|---|---|
| fresh-4096-256 | 27070 | 0 | False | True |
| fresh-4096-4096 | 14781 | 0 | False | True |
| fresh-65536-256 | 14719 | 0 | False | True |
| fresh-65536-4096 | 11395 | 0 | False | True |
| persistent-4096-256 | 135402 | 0 | True | False |
| persistent-4096-4096 | 77823 | 0 | False | True |
| persistent-65536-256 | 24107 | 0 | False | True |
| persistent-65536-4096 | 26746 | 0 | False | True |

Framework fingerprint: `4d5b4ee0ee148f9c579d973aee7253ae5ac08281e4ce31c28771e3e760f20c23`.

Proxy/upstream calibration is not established by this static probe. Resolve the
generator bottleneck before new performance-comparison campaigns.
