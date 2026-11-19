# Security audit — run afdc173f — release/000001 (round 10, lane M)

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
| SEC-001 | yes | low | The cache keys on the raw target, so every spelling of one resource is a separate entry | line 75 (`cachebase`) | `evidence/ev_r10_M_afdc_36120_36120.json` |

## Findings

### SEC-001 — The cache keys on the raw target, so every spelling of one resource is a separate entry

cachebase is `"http://"+host+target` with the untouched target, so `%2f`, uppercase hex, a trailing `&` and a trailing slash are all distinct keys for the same decoded resource. 40 of 40 cross-spelling reads re-executed (counter incremented). A client that spells the token differently is not served the attacker's entry. Host casing is normalised and does hit the same key; only the target is raw.

Evidence: `evidence/ev_r10_M_afdc_36120_36120.json`

## Artifact index

- `evidence/ev_r10_M_afdc_36120_36120.json`

## Limitations

- Upstream-host execution only.
- Needs a cache-enabled config and a cacheable upstream response.
