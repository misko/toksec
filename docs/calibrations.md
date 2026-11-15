# Benchmark calibration evidence

`calibrations/<calibration-id>/` stores checks of the measurement machinery.
`results/<run-id>/` stores evidence about submitted implementations.

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
