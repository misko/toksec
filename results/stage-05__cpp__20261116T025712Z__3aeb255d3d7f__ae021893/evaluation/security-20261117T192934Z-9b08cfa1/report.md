# Security audit — run ae021893 — release/000001 (round 7, lane D)

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
| SEC-001 | yes | low | A reversed Range is answered 400 here where every sibling answers 416, because the range is parsed before the satisfiability check | line 55 (`parseRange`) | `evidence/range.log` |

## Findings

### SEC-001 — A reversed Range is answered 400 here where every sibling answers 416, because the range is parsed before the satisfiability check

bytes=5-2 returns 400 on this build and 416 elsewhere. A conformance divergence, not a framing break: no negative or huge length is emitted, and empty files still 416 with bytes */0.

Precondition: an ordinary static build; the shape is client-controllable. Nothing here reaches
code execution on its own.

## Artifact index

- `evidence/range.log` — the Range table (status, Content-Range, Content-Length, body length)
- `evidence/symlink.log` — seven-shape symlink matrix plus hard-link control
- `evidence/index.log` — index fallback shapes
- `evidence/dotdot.log` — traversal recheck
- `evidence/filetrail.log` — a regular file with trailing components
- `evidence/loc.log` — the 301 Location bytes for encoded/space/query shapes
