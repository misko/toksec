# Stage 5: Plaintext operations

Independent from-scratch assignment. Implement all capabilities in the resolved
contract; no earlier stage implementation is provided.

This profile is plaintext only: no TLS, encryption or compression libraries.
TLS and gzip are not requirements in this version.

Configuration limits may vary. Apply backpressure to pipelines beyond pipeline_depth
without dropping ordered requests. Close stalled writes after write_timeout_ms
and release their connection slots. Other clients must remain serviceable.
