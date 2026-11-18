# Security audit — run 6baf167b — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Two fresh servers, two runs each: the client sends the head, waits, and receives `eof` at exactly 2.00 s with an empty response (`hex=` empty, r0 and r1 identical). The `Expect: 100-continue` header is copied to the upstream verbatim by the `:97` loop but nothing in the proxy answers the contract, so a compliant client either times out or writes blindly into a socket the proxy is about to close.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | No `100 Continue` is ever synthesised, so a client that correctly waits for it is closed with zero bytes after 2 s | line 97 (`r.h`) | `evidence/ev_r11_R_st6baf167b.st.txt` |

## Findings

### SEC-001 — No `100 Continue` is ever synthesised, so a client that correctly waits for it is closed with zero bytes after 2 s

Two fresh servers, two runs each: the client sends the head, waits, and receives `eof` at exactly 2.00 s with an empty response (`hex=` empty, r0 and r1 identical). The `Expect: 100-continue` header is copied to the upstream verbatim by the `:97` loop but nothing in the proxy answers the contract, so a compliant client either times out or writes blindly into a socket the proxy is about to close.

Evidence: `evidence/ev_r11_R_st6baf167b.st.txt`

## Artifact index

- `evidence/ev_r11_R_st6baf167b.st.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
