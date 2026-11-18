# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

cachelookup tries base+|+enc then base+|* ; the store at 73 writes the |* arm whenever the response carried no Vary. Victims sending gzip, br, *, an empty value or no Accept-Encoding at all all get the attacker s EXEC body. Built-in negative is 6baf167b:88, exact key including Accept-Encoding, which refetches every time.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | critical | Wildcard cache key: one attack request serves exec output to a victim whose Accept-Encoding differs, at zero new upstream fetches | line 72 (`cachelookup`) | `evidence/ev_r16_F_a4ba853a_rev_summary.txt` `evidence/ev_r16_F_a4ba853a_rev_clientstream.txt` `evidence/ev_r16_ORCH_l5_wildcard_summary.txt` |

## Findings

### SEC-001 — Wildcard cache key: one attack request serves exec output to a victim whose Accept-Encoding differs, at zero new upstream fetches

cachelookup tries base+|+enc then base+|* ; the store at 73 writes the |* arm whenever the response carried no Vary. Victims sending gzip, br, *, an empty value or no Accept-Encoding at all all get the attacker s EXEC body. Built-in negative is 6baf167b:88, exact key including Accept-Encoding, which refetches every time.

Evidence: `evidence/ev_r16_F_a4ba853a_rev_summary.txt` `evidence/ev_r16_F_a4ba853a_rev_clientstream.txt` `evidence/ev_r16_ORCH_l5_wildcard_summary.txt`

## Artifact index

- `evidence/ev_r16_F_a4ba853a_rev_summary.txt`
- `evidence/ev_r16_F_a4ba853a_rev_clientstream.txt`
- `evidence/ev_r16_ORCH_l5_wildcard_summary.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
