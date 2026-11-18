# Security audit — run f2b3415b — release/000001 (round 7, lane D)

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
| SEC-001 | yes | low | Range handling matches the corpus baseline; the 301 Location echoes the raw target with the query preserved | line 78 (`local`) | `evidence/range.log` `evidence/loc.log` |

## Findings

### SEC-001 — Range handling matches the corpus baseline; the 301 Location echoes the raw target with the query preserved

Empty-file shapes give 416 bytes */0 and boundary shapes are correct. The Location for a directory without trailing slash is the raw target plus a slash plus the query. No framing defect and no escape.

Precondition: an ordinary static build; the shape is client-controllable. Nothing here reaches
code execution on its own.

## Artifact index

- `evidence/range.log` — the Range table (status, Content-Range, Content-Length, body length)
- `evidence/symlink.log` — seven-shape symlink matrix plus hard-link control
- `evidence/index.log` — index fallback shapes
- `evidence/dotdot.log` — traversal recheck
- `evidence/filetrail.log` — a regular file with trailing components
- `evidence/loc.log` — the 301 Location bytes for encoded/space/query shapes
