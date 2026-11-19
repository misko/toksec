# Security audit — run 6baf167b — release/000001 (round 7, lane D)

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
| SEC-001 | yes | low | An empty-file Range computes end=0 while length stays 0, so the 206 header set is planned for a body that cannot exist | line 83 (`size`) | `evidence/range.log` |

## Findings

### SEC-001 — An empty-file Range computes end=0 while length stays 0, so the 206 header set is planned for a body that cannot exist

Range on a 0-byte file is answered 416 with Content-Range: bytes */0 and Content-Length: 0 on every shape, so the suspected -1 length never reaches the client; the size?size-1:0 clamp is hidden by the 416 path. No framing break.

Precondition: an ordinary static build; the shape is client-controllable. Nothing here reaches
code execution on its own.

## Artifact index

- `evidence/range.log` — the Range table (status, Content-Range, Content-Length, body length)
- `evidence/symlink.log` — seven-shape symlink matrix plus hard-link control
- `evidence/index.log` — index fallback shapes
- `evidence/dotdot.log` — traversal recheck
- `evidence/filetrail.log` — a regular file with trailing components
- `evidence/loc.log` — the 301 Location bytes for encoded/space/query shapes
