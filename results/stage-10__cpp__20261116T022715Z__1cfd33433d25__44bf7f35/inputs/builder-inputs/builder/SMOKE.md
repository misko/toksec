# Minimal visible smoke checks

The host supplies these descriptions and ordinary example inputs. It does not
ship the checker implementation or its edge-case fixtures to the builder.

1. bootstrap: one ordinary plaintext GET of /hello.txt returns 200, exact bytes,
   Content-Length and a closing response to Connection: close. This uses the separate minimal bootstrap.conf and is the first-tag eligibility gate.
2. config: --check-config accepts the ordinary supplied nginx.conf and exits zero.
3. https-get: one ordinary HTTPS GET returns the same file, with trusted fixture
   CA and hostname verification enabled by the client.
4. https-persistent: two sequential ordinary GETs on one HTTPS connection succeed.
5. proxy: one ordinary proxied GET returns the fixture upstream's exact body.

A tag may be published once bootstrap passes. Every new tag must compile, pass
bootstrap and preserve previously passing visible checks. Missing later checks
are recorded as incomplete rather than preventing every early release. Smoke
success does not establish final API correctness or final performance eligibility.

There are deliberately no visible tests for malformed syntax, large headers,
missing fields, TLS negotiation edge cases, worker crashes or overload. Design
your own tests from the complete public contract. Their absence from the smoke
suite does not remove them from the assignment.
