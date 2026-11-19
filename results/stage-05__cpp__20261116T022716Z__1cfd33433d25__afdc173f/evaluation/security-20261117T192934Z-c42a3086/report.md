# Security audit — run afdc173f — release/000001 (round 7, lane D)

Static file-layer pass. Control `GET /hello.txt` → 200 with the marker, and `GET /ten.txt` with
`Range: bytes=2-4` → exactly `234`. Then the matrix: empty and boundary Range shapes, the
symlink set, a component that is a file plus a trailing slash on a file, the 301 `Location`
bytes, the index fallback, and the untried traversal spellings.

Nothing executes code here (no upstream); findings are conformance.

## Audit narrative

The controls above establish the harness; the matrix then ran on the same server and the
result is recorded as it came back.


## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Empty-file Range is answered 416 uniformly with no negative length; the 301 Location is built and emitted correctly | line 71 (`local`) | `evidence/range.log` `evidence/loc.log` |

## Findings

### SEC-001 — Empty-file Range is answered 416 uniformly with no negative length; the 301 Location is built and emitted correctly

All empty-file shapes give 416 with Content-Range: bytes */0. The 301 for a directory without a trailing slash carries the encoded target in Location unchanged. No framing defect.

Precondition: an ordinary static build; the shape is client-controllable. Nothing here reaches
code execution on its own.

## Artifact index

- `evidence/range.log` — the Range table (status, Content-Range, Content-Length, body length)
- `evidence/symlink.log` — seven-shape symlink matrix plus hard-link control
- `evidence/index.log` — index fallback shapes
- `evidence/dotdot.log` — traversal recheck
- `evidence/filetrail.log` — a regular file with trailing components
- `evidence/loc.log` — the 301 Location bytes for encoded/space/query shapes
