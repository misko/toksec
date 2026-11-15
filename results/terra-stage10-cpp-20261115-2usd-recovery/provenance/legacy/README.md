# Stage 10 — C++ / Terra

Final submission: **release/000007**, preserved in `implementation.bundle` and
`main.cpp`. All seven tagged source versions and visible smoke reports are included.
No starter code was supplied. Terra implemented the server and OpenSSL integration.

The final tag passes all six visible smoke checks. Independent partial evaluation
passes **50 of 57 behavioral checks**; the raw report also includes a failed
orchestration summary (`api-runtime`), yielding 50/58 rows. Failures concern malformed
request handling, chunked proxy transfers, cache behavior and streaming progress.
Full Stage 10 acceptance is not established. No performance benchmarks were run.

Total conservative accounted spend: **$1.92574750 of $2.00** across both attempts.
The initial context-retention failure cost $0.30209125; the recovery cost $1.62365625.
Both are recorded in `ledger.json`. No charges remain pending. The recovery builder
finished in about nine minutes; the campaign ceiling was two hours.

`builder-inputs/` and `launch-packet.md` preserve supplied instructions and fixtures.
TLS private keys here are public test fixtures, not host credentials. `attempts/`
preserves both launch packets/manifests. API conversation logs and credentials are
excluded. Raw runs remain untouched at the paths recorded in `run.json` and the ledger.

Restore the complete standalone Git repository, including all release tags:

```sh
git clone /home/mouse9911/gits/toksec-next/results/stage-10/cpp/implementation.bundle /path/to/stage10-repository
git -C /path/to/stage10-repository checkout release/000007
```

This is a preserved experimental snapshot. The Stage 1–5 refresh script retains its
inventory entry but does not regenerate it. See `run.json` for protocol identity.
