# Benchmark calibration evidence

`calibrations/<calibration-id>/` stores checks of the measurement machinery.
`results/<run-id>/` stores evidence about submitted implementations.
The static HTTP probe source lives in
`stages/common/grading/probes/load_reference.cpp` and is never a builder input.

New calibrations record their Toksec commit, dirty-checkout flag, probe source
hash, environment and workload measurements. Run `python3 scripts/calibrate_benchmarks.py`
to create an identified calibration. This runs local benchmarks, not model calls.
`--output DIRECTORY` remains available for temporary diagnostics.

The index lists records without automatically treating the newest as applicable.
Compare workload, machine, resource limits and framework before using a calibration.
The historical static HTTP record preserves the original JSON and README with a
checksum mapping. Its missing Git commit remains unknown; its framework fingerprint
is not a Git commit. Seven workloads remain ineligible. Relocation did not rerun
the measurements or resolve generator saturation.

## Calibrate gateway workloads

Run the parent CLI on the CPU slot intended for grading. Supply an archived or reference C++ source whose provenance you can verify. The command rebuilds it and runs the independent API checks on the supplied source and a deliberately slower control. Measurement starts only after both pass.

```sh
taskset -c 12,13,14,18,20,23 python3 scripts/calibrate_benchmarks.py \
    --stage 14 --reference /path/to/sealed/main.cpp --output /path/to/new-calibration
```

Stage 16 uses the same command with `--stage 16`. Repeat `--workload` to select a diagnostic subset. The default measures all declared cells. A calibration with fewer than five rounds records diagnostics and cannot qualify a cell. Use a new output directory for each attempt.

Each cell includes direct target observations and five counterbalanced reference, repeated-reference and slower-source rounds. Slower-source rounds use the same server with a 35-microsecond thread CPU cost on each send. Positive control and A/A comparisons require healthy fixtures, successful responses and verified effects. Direct targets measure capacity ceilings. A direct target may saturate while demonstrating more valid traffic than the in-path server. All its deliveries must succeed and its observed median goodput must exceed the in-path median by 5%.

The gateway diagnostic uses admitted traffic with 4 KiB bodies and 256 clients. Independent confirmation uses 4,096 clients and the same body size. Inspect `diagnostic_ready`, `confirmation_ready`, and `full_matrix_ready` separately. A complete record carries its measurement fingerprint, source hashes, CPU allocation, kernel, calibration ID, per-cell causes and underlying raw rounds.

Stage 14 and Stage 16 performance rounds use four CPU-pinned native clients.
Each client validates the HTTP status, framing, and every payload byte before
recording a successful request. Each round identifies its generator in
`generator_implementation` and reports client utilization, event-loop lag,
origin utilization, failures by category, and valid throughput.
