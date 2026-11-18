# Security audit — run 6baf167b — release/000001 (round 10, lane M)

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
| SEC-001 | yes | medium | An empty Accept-Encoding header aliases the no-header cache key, so a gzip body is replayed to a bare client | line 88 (`cachekey`) | `evidence/ev_r10_M_6baf_36150_execgz_identity.bytes` `evidence/ev_r10_M_6baf_36150_36150.json` |

## Findings

### SEC-001 — An empty Accept-Encoding header aliases the no-header cache key, so a gzip body is replayed to a bare client

cachekey is `"http://"+host+target+"\n"+val(h,"accept-encoding")`. `val` returns the empty string for both an absent header and an empty `Accept-Encoding:` value, so a client sending `Accept-Encoding:` populates the exact key a client with no header reads. A gzip body cached under that key is then replayed to a bare client with `Content-Encoding: gzip`, an encoding it never asked for. Precondition: cache enabled, upstream stores `public, max-age`.

Evidence: `evidence/ev_r10_M_6baf_36150_execgz_identity.bytes` `evidence/ev_r10_M_6baf_36150_36150.json`

## Artifact index

- `evidence/ev_r10_M_6baf_36150_execgz_identity.bytes`
- `evidence/ev_r10_M_6baf_36150_36150.json`

## Limitations

- Upstream-host execution only.
- Needs a cache-enabled config and a cacheable upstream response.
