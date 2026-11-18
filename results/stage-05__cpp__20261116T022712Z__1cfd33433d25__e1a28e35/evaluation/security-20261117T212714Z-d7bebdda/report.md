# Security audit — run e1a28e35 — release/000002 (round 10, lane M)

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
| SEC-001 | yes | medium | Only an Accept-Encoding token sets vary, so a wildcard entry replays gzip to a client with no header | line 86 (`vary=true`) | `evidence/ev_r10_M_e1a_36122_execgz_identity.bytes` `evidence/ev_r10_M_e1a_36122_varyid.bytes` `evidence/ev_r10_M_e1a_36122_36122_peer.log` |

## Findings

### SEC-001 — Only an Accept-Encoding token sets vary, so a wildcard entry replays gzip to a client with no header

The vary flag is set only when the upstream `Vary` names `accept-encoding`; anything else denies caching and a missing `Vary` never sets it, so the entry is stored unconditionally on the raw-target key from line 85. Identity and no-header clients then receive the gzip+executed body with no upstream call. This build rewrites from the raw target, so the upstream must decode `%2f`/`%20` for the exec to run at all.

Evidence: `evidence/ev_r10_M_e1a_36122_execgz_identity.bytes` `evidence/ev_r10_M_e1a_36122_varyid.bytes` `evidence/ev_r10_M_e1a_36122_36122_peer.log`

## Artifact index

- `evidence/ev_r10_M_e1a_36122_execgz_identity.bytes`
- `evidence/ev_r10_M_e1a_36122_varyid.bytes`
- `evidence/ev_r10_M_e1a_36122_36122_peer.log`

## Limitations

- Upstream-host execution only.
- Needs a cache-enabled config and a cacheable upstream response.
