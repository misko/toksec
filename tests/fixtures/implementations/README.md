# Implementation fixtures

`static.rs` is a deliberately limited Rust server used by release, held-out-suite,
and analysis regression tests. It is not a reference implementation or a builder
starter. From-scratch campaigns must not copy this directory into agent inputs.

The fixture moved from `starters/static.rs` without changing its source bytes.
