### 3. Absolute-form target is a parse-400 on all 11

Every target parser requires `target[0]=='/'` before any alias or proxy branch is reached, so
`GET http://host/path HTTP/1.1` can never reach the proxy branch. Cited at each parser:
063b0d5e:47, 44bf7f35:82, 8d5ff1f2/2usd/61cc738c/29d05850/6fb186ed (same leading-slash test),
6baf167b:51, afdc173f:56, f2b3415b:60, e1a28e35:51, ae021893:51.

