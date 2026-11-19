# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The same key is parsed with a zero flag on afdc173f and without on a4ba853a:42, so a4ba853a refuses to start on cache_bytes=0 while afdc173f starts with an inert cache. Operational hazard for anyone copying a cache config between the two.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Parser divergence: cache_bytes=0 is fatal on one build and accepted-and-inert on the sibling | line 42 (`num`) | `evidence/ev_r16_F_a4ba853a_nocache_summary.txt` |

## Findings

### SEC-001 — Parser divergence: cache_bytes=0 is fatal on one build and accepted-and-inert on the sibling

The same key is parsed with a zero flag on afdc173f and without on a4ba853a:42, so a4ba853a refuses to start on cache_bytes=0 while afdc173f starts with an inert cache. Operational hazard for anyone copying a cache config between the two.

Evidence: `evidence/ev_r16_F_a4ba853a_nocache_summary.txt`

## Artifact index

- `evidence/ev_r16_F_a4ba853a_nocache_summary.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
