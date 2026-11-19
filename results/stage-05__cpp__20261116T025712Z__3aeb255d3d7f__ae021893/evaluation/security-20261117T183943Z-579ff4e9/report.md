# Security audit delta — stage-05 run ae021893 — release/000001 (round 7)

Second pass on the audited release `release/000001` (56 lines). The first envelope covered the
separator RCE and the cache findings. This pass adds the vhost/alias ordering: the host
selects a root, and the alias branch then overwrites it, so a confined vhost can read the
alias root.

The bypass is a **read-scope** finding: no executor is reached here, so it is not itself RCE.
It matters because it defeats the vhost confinement an operator configured, and because any
executable the upstream would honour in the alias root becomes reachable from the wrong
vhost.

## Audit narrative

The local branch sets root from host_root on Host match, then replaces root with the alias root whenever the decoded path starts with the alias prefix.

Host validation has already completed when this happens, so nothing re-checks that the alias
root belongs to the vhost that won. With `host_root=beta.test:/www/beta` and
`alias=/alias:/www/alias`, `GET /ten.txt` on `Host: beta.test` correctly 404s (beta is
confined) while `GET /alias/hello.txt` on the same vhost returns the alias root's file, and
`GET /alias/` returns the alias `index.html`. The `%2f` spelling of the separator decodes
before the compare and reaches the same root. `..` stays refused on this branch.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | no | medium | The alias branch overwrites the vhost-selected document root after host validation, so a confined vhost reads the alias root | line 56 (`aliasroot`) | `evidence/alias_bypass.log` |
| SEC-002 | no | low | The alias prefix is matched on the decoded path, so the `%2f` spelling reaches the same alias root and defeats a raw-prefix check in front of the proxy | line 56 (`aliasroot`) | `evidence/alias_bypass.log` |

## Findings

### SEC-001 — vhost isolation bypass

Control 1: `GET /hello.txt` on `Host: alpha.test` → 200. Control 2: `GET /ten.txt` on
`Host: beta.test` → 404, proving beta does not see the alpha root. Then
`GET /alias/hello.txt` on `Host: beta.test` → 200 with the alias marker. The vhost boundary
the operator declared is not the boundary the server enforces.

### SEC-002 — encoded spelling of the same bypass

`GET /alias%2fhello.txt` returns the same file. Since the match is on the decoded path, the
encoding is invisible to it while remaining visible to anything that inspects the raw URL
first.

## Artifact index

- `evidence/alias_bypass.log` — the four-build matrix, both controls, plain and `%2f`
  bypasses, index case, `..` negative

## Limitations

- One build here; the same ordering exists in four siblings, which carry their own envelopes
  with the same evidence matrix.
- Read-scope only: the alias root holds no executor in this test.
- `..` is guarded, so this does not leave the alias subtree.
