# Artifact ownership and submission format

The supplied `artifact.json` defines your source filename, UTF-8 encoding, size
limit, and release-tag format. Submit the complete source through
`submit_candidate`. The controller validates the contract and writes the required
filename. Do not choose a different submission path or create parent-owned files.

The controller owns `release.json` and creates numbered Git tags when you call
`init_repository` or `release_candidate`. On stages with an optional
`release_note` argument, a submission or edit can request a tag in the same call.
Only the last completed tag is the final
submission. Untagged changes and claims in a report do not replace that tag.

The parent publishes the frozen implementation separately from independent API
results, performance measurements, reports, and figures. You do not write the
parent's evaluation files or choose their destination. Development smoke feedback
and your own tests are not parent acceptance evidence.
