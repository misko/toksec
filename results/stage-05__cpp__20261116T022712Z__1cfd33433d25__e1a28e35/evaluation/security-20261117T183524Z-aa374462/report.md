# Security audit delta — stage-05 run e1a28e35 — release/000002 (round 6/7)

Second pass on the audited release `release/000002` (91 lines). The first envelope covered
the separator RCE and the cache findings. This pass adds the vhost/alias boundary: host
validation selects one root, and the alias branch then overwrites it, so the alias root is
reachable from a vhost that is supposed to be confined.

The served-root bypass is a **read-scope** finding (no executor is reached), and it is what
turns an unrelated `alias` directive into a cross-vhost exposure.

## Audit narrative

The local branch computes `root = host==bhost ? broot : root` and then, if the decoded path
begins with the alias prefix, replaces the root with the alias root (`line 72 (aliasroot)`).
The host check has already happened by then, so nothing re-checks that the alias root belongs
to the vhost that won.

Concretely, with `host_root=beta.test:/www/beta` and `alias=/alias:/www/alias`, the beta
vhost is properly confined for ordinary paths — an alpha-only file 404s on beta — but
`GET /alias/hello.txt` with `Host: beta.test` returns the alias root's file. `GET /alias/`
returns the alias `index.html`. Since `%2f` also decodes into the prefix region, the encoded
spelling works identically. `..` stays refused on this branch.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | no | medium | The alias branch overwrites the vhost-selected document root after host validation, so a confined vhost reads the alias root | line 72 (`aliasroot`) | `evidence/e1a_alias.log` |
| SEC-002 | no | low | The alias prefix is matched on the decoded path, so `%2f` spelling reaches the same alias root and bypasses nothing extra but hides the path from the vhost | line 72 (`aliasroot`) | `evidence/e1a_alias.log` |

## Findings

### SEC-001 — vhost isolation bypass through the alias root

Precondition: both `host_root` and `alias` configured, and content in the alias root the
vhost should not serve. Request: `GET /alias/hello.txt` with `Host: beta.test` → 200 with the
alias marker while `/ten.txt` on the same vhost is 404. Classification: isolation bypass.

It becomes RCE-adjacent only if the alias root holds something an upstream would execute
(a `.php`/`.cgi` served verbatim, or a config an executor reads); the proxy itself does not
run code.

### SEC-002 — decoded-match encoding of the same bypass

`GET /alias%2fhello.txt` returns the same file. `%2f` decodes to the separator that makes the
prefix compare succeed, so the bypass has an encoded spelling that a naive raw-prefix check
in front of the proxy would miss.

## Artifact index

- `evidence/e1a_alias.log` — both controls, the bypass in plain and `%2f` form, the index
  cases, and the `..` negatives

## Limitations

- One build; the same ordering exists in its four siblings, which carry their own envelopes.
- Read-scope only on this build: no executor in the alias root here.
- `..` is guarded, so this does not reach outside the alias root.
