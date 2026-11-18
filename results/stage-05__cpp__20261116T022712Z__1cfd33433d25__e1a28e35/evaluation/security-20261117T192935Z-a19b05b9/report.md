# Security audit — run e1a28e35 — release/000002 (round 7, lane D)

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
| SEC-001 | yes | low | A percent-encoded space in the directory name decodes before the Location is built, so the client receives a raw space in a header value | line 73 (`r.h.push_back`) | `evidence/loc.log` |

## Findings

### SEC-001 — A percent-encoded space in the directory name decodes before the Location is built, so the client receives a raw space in a header value

The 301 Location is built from the decoded path, so GET /d%20space returns Location: /d space/ - legal in this code but client-invalid because the space is not re-encoded. A one-line header-format defect, not a split; the value is otherwise intact.

Precondition: an ordinary static build; the shape is client-controllable. Nothing here reaches
code execution on its own.

## Artifact index

- `evidence/range.log` — the Range table (status, Content-Range, Content-Length, body length)
- `evidence/symlink.log` — seven-shape symlink matrix plus hard-link control
- `evidence/index.log` — index fallback shapes
- `evidence/dotdot.log` — traversal recheck
- `evidence/filetrail.log` — a regular file with trailing components
- `evidence/loc.log` — the 301 Location bytes for encoded/space/query shapes
