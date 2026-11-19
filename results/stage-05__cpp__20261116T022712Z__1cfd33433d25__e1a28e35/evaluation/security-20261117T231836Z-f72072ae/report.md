# Security audit — run e1a28e35 — release/000002 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Byte-identical client and upstream hex to 6baf167b with only the port differing: the `100` aborts, the client sees `502` then `200` with `SEQ:2 EXEC:uid=1000`, body re-parsed and executed 2/2. The forwarding loop at `:84` iterates `req.h` in client order with only the hop-by-hop set removed, so the `Expect` header reaches the upstream verbatim and is what provokes the interim response.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Same interim-`100` abort into 502 with the body re-parsed and executed upstream, on a client-order header loop | line 84 (`hop.count`) | `evidence/ev_r11_R_e1a2.iso.txt` `evidence/ev_r11_R_e1a2.wait100.txt` |

## Findings

### SEC-001 — Same interim-`100` abort into 502 with the body re-parsed and executed upstream, on a client-order header loop

Byte-identical client and upstream hex to 6baf167b with only the port differing: the `100` aborts, the client sees `502` then `200` with `SEQ:2 EXEC:uid=1000`, body re-parsed and executed 2/2. The forwarding loop at `:84` iterates `req.h` in client order with only the hop-by-hop set removed, so the `Expect` header reaches the upstream verbatim and is what provokes the interim response.

Evidence: `evidence/ev_r11_R_e1a2.iso.txt` `evidence/ev_r11_R_e1a2.wait100.txt`

## Artifact index

- `evidence/ev_r11_R_e1a2.iso.txt`
- `evidence/ev_r11_R_e1a2.wait100.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
