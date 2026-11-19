# Public test credentials

Every private key in this directory is a deliberately public, generated test
fixture for alpha.test or beta.test. Never use these keys for a deployed service.
The CA signing key is not retained or delivered to the builder. ca.pem is the
trust certificate only. Replacement leaves use distinct keys and serial numbers.

Certificate validity is finite. Fixture metadata records the generation time and
verification results. Launch preflight must verify the whole intended run interval
fits within validity, or regenerate/re-hash the fixture packet before the run.
Independent host tests generate their own keys and names; these examples are not
the comprehensive TLS test suite.
