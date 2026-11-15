# Historical accounting fixture

`legacy-pilot-ledger.json` is the unchanged ledger from the original Luna Python
pilot, previously stored at `fixtures/accounting/legacy-pilot-ledger.json`.
Its original location is preserved in Git commit
`180c8c1b01777917789b990f6928370b2a38da3c`. This file is historical evidence used
to test explicit ledger import. Fresh campaigns do not read it.

Import records the source SHA-256 and path. Moving this fixture does not rewrite
old campaign ledgers, manifests, reports, or their recorded hashes.
