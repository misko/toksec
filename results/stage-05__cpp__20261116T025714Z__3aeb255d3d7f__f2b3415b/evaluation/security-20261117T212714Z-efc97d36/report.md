# Security audit — run f2b3415b — release/000001 (round 10, lane M)

Cache key equality and `Vary` omission. Release source read from the tag and byte-identical to
the staged copy.

All RCE is RCE on the **upstream host**; the proxy builds a request line and the upstream runs it.

## Audit narrative

Control first on the same config. Eight raw-target spellings (A `%2f`+`%20`, B plain separator,
C literal space, D uppercase hex, E trailing `&`, F uppercase path, G trailing slash, H double
slash) crossed with four `Accept-Encoding` classes (gzip seed, identity, no header, empty header),
with a per-request exec counter so a cache hit is distinguishable from a fresh execution. A
`gzipvary` control that must re-execute across encodings guards the Vary leg.

Answer: no spelling pair produced an identical raw key on any of the five builds (40/40 cross
pairs missed), so the exec entry is per-spelling. The Vary leg is real: a `Vary`-less cached
response installs an unconditional entry that is then served to clients that never negotiated
gzip, with `Content-Encoding: gzip` and a gzip body.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A Vary-less response is keyed as `\n*` and tried before the encoding key, so gzip reaches identity clients | line 81 (`cachekey`) | `evidence/ev_r10_M_f2b_36132_varyid.bytes` `evidence/ev_r10_M_f2b_36132_36132.json` |

## Findings

### SEC-001 — A Vary-less response is keyed as `\n*` and tried before the encoding key, so gzip reaches identity clients

cachekey appends `"\n*"` when the upstream sent no `Vary`, and cacheget at line 83 tries the vary key then the wildcard. The no-Vary gzip entry is therefore served to identity and no-header clients without re-calling the upstream.

Evidence: `evidence/ev_r10_M_f2b_36132_varyid.bytes` `evidence/ev_r10_M_f2b_36132_36132.json`

## Artifact index

- `evidence/ev_r10_M_f2b_36132_varyid.bytes`
- `evidence/ev_r10_M_f2b_36132_36132.json`

## Limitations

- Upstream-host execution only.
- Needs a cache-enabled config and a cacheable upstream response.
