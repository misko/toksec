# Framework regression tests

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Enable the Stage 10 live sandbox integration tests on a Linux host with delegated
user-systemd cgroups and the required compilers/OpenSSL installation:

```sh
TOKSEC_STAGE10_SANDBOX_TEST=1 python3 -m unittest discover -s tests -v
```

The ordinary suite already runs sandboxed build/server regressions. The explicit
Stage 10 tests additionally check aggregate resource enforcement and process-tree
cleanup. Fake-provider tests make no model API calls. The optional independent
JSON Schema cross-check is skipped if `jsonschema` is unavailable.

These tests validate the framework, not acceptance of every server implementation.
Server acceptance suites live in `stages/stage-XX/grading/` and reuse checks from
`stages/common/grading/`. `toksec/` executes those suites; Stage 10's independent
coverage remains partial. Minimal development checks live in `stages/common/smoke/`.
These framework tests also verify that builder inputs exclude comprehensive graders.
Files under
`tests/fixtures/implementations/` are test-only server sources and must never be
included in builder packets.
