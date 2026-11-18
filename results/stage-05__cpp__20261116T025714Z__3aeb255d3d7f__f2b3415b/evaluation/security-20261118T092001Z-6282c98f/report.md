# Security audit — run f2b3415b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same retry shape but the retry consumes the pool, so it needs two upstreams; POST is not retried.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A partial-body GET is retried from byte 0 and needs a second upstream | line 86 (`upfail`) | `evidence/ev_r15_G_f2b_pg.log` |

## Findings

### SEC-001 — A partial-body GET is retried from byte 0 and needs a second upstream

Same retry shape but the retry consumes the pool, so it needs two upstreams; POST is not retried.

Evidence: `evidence/ev_r15_G_f2b_pg.log`

## Artifact index

- `evidence/ev_r15_G_f2b_pg.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
