### 4. CONNECT: no build implements tunneling

Method validation accepts CONNECT as a valid token, but no source contains the literal
CONNECT (`grep -c CONNECT` = 0 in all 12 sources), no tunnel branch exists, and every proxy
branch still emits `method + path` upstream or 405s non-GET methods. The arbitrary byte pipe
CONNECT would create is closed for all builds; a live status line was not captured.

