# Security audit — run 6baf167b — release/000001 (round 11, lane B)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

B census: the SIGHUP handler re-parses the config file. Nothing in the build writes a file it later reads (ofstream/fopen/O_CREAT/O_TRUNC/rename/unlink all zero), so a reload can change routing but cannot introduce code. Seven builds share this shape; 6baf167b is the strongest because it also has a cache.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Config is re-read from the operator s file on SIGHUP with no write path, so the reload is parsed nginx syntax but never a shell | line 110 (`SIGHUP`) | `evidence/ev_r16_B_census.md` `evidence/ev_r16_B_execproof.sh` |

## Findings

### SEC-001 — Config is re-read from the operator s file on SIGHUP with no write path, so the reload is parsed nginx syntax but never a shell

B census: the SIGHUP handler re-parses the config file. Nothing in the build writes a file it later reads (ofstream/fopen/O_CREAT/O_TRUNC/rename/unlink all zero), so a reload can change routing but cannot introduce code. Seven builds share this shape; 6baf167b is the strongest because it also has a cache.

Evidence: `evidence/ev_r16_B_census.md` `evidence/ev_r16_B_execproof.sh`

## Artifact index

- `evidence/ev_r16_B_census.md`
- `evidence/ev_r16_B_execproof.sh`

## Limitations

- All RCE in this corpus is RCE on the upstream host
