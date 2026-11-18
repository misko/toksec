# Security audit — run ae021893 — release/000001 (round 10, lane M)

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
| SEC-001 | yes | low | One global cache map across Host, so a beta-vhost fill evicts an alpha exec entry | line 67 (`cachekey`) | `evidence/ev_r10_M_e6b_36140_evict.json` |

## Findings

### SEC-001 — One global cache map across Host, so a beta-vhost fill evicts an alpha exec entry

The cache is a single map shared by every vhost. With a small `cache_bytes`, filling it from `Host: beta.test` evicts the alpha exec entry, and the next alpha client re-executes instead of being served the cached page. Reproduced on all five cache builds with `cache_bytes=260` and six fill pages.

Evidence: `evidence/ev_r10_M_e6b_36140_evict.json`

## Artifact index

- `evidence/ev_r10_M_e6b_36140_evict.json`

## Limitations

- Upstream-host execution only.
- Needs a cache-enabled config and a cacheable upstream response.
