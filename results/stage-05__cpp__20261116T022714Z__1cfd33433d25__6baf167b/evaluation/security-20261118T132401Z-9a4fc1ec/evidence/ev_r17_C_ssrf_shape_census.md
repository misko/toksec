### 7. SSRF / confused-deputy shape

Source-confirmed: the proxy always dials the configured `upstreams`/`upstream backend` port
(063b0d5e:56-59, 44bf7f35:87, 8d5ff1f2:…, 2usd:78, 61cc738c:67, 29d05850:50,
6baf167b:96-99). There is no variable proxy_pass and no request-derived port anywhere in the
12 sources, so the client cannot make the proxy connect anywhere else. The Q7
confused-deputy SSRF therefore reduces to the configured upstream itself; proving
“client cannot address directly” needs a network namespace the container does not grant
(`unshare -n` returned Operation not permitted).

