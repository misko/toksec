# Security audit — run f2b3415b — release/000001 (round 11, lane S)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Control first on the same config. `startup` pops the pooled fd and treats `recv(MSG_PEEK|MSG_DONTWAIT)` returning EAGAIN as reusable (`:87`); `delup` returns the fd whenever the head was HTTP/1.1 without `Connection: close` (`:89`, `:71`). A peer that holds one response back and flushes it after the peek hands the victim the attacker's frame byte for byte, 10/10 from cold servers, exec output included. Separate defect on `:86`: `upfail` retries only GET/HEAD, so a dead pooled socket is fatal to a POST — 20/20 POST 502 while GET is retried away when a second upstream exists.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Pool liveness is a one-byte check-then-use with no epoch, so a frame the upstream writes after the peek is served to the next client as its own response | line 87 (`MSG_PEEK`) | `evidence/ev_r11_S_headline_3aeb255d3d7f__f2b3415b.txt` `evidence/ev_r11_S_cold_f2b.txt` `evidence/ev_r11_S_window_f2b_d2_2ups_post.txt` |

## Findings

### SEC-001 — Pool liveness is a one-byte check-then-use with no epoch, so a frame the upstream writes after the peek is served to the next client as its own response

Control first on the same config. `startup` pops the pooled fd and treats `recv(MSG_PEEK|MSG_DONTWAIT)` returning EAGAIN as reusable (`:87`); `delup` returns the fd whenever the head was HTTP/1.1 without `Connection: close` (`:89`, `:71`). A peer that holds one response back and flushes it after the peek hands the victim the attacker's frame byte for byte, 10/10 from cold servers, exec output included. Separate defect on `:86`: `upfail` retries only GET/HEAD, so a dead pooled socket is fatal to a POST — 20/20 POST 502 while GET is retried away when a second upstream exists.

Evidence: `evidence/ev_r11_S_headline_3aeb255d3d7f__f2b3415b.txt` `evidence/ev_r11_S_cold_f2b.txt` `evidence/ev_r11_S_window_f2b_d2_2ups_post.txt`

## Artifact index

- `evidence/ev_r11_S_headline_3aeb255d3d7f__f2b3415b.txt`
- `evidence/ev_r11_S_cold_f2b.txt`
- `evidence/ev_r11_S_window_f2b_d2_2ups_post.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
