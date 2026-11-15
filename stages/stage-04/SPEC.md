# Stage 4: Reverse proxy

Independent from-scratch assignment. Implement all capabilities in the resolved
contract; no earlier stage implementation is provided.


Configuration limits may vary. Apply backpressure to pipelines beyond pipeline_depth
without dropping ordered requests. Close stalled writes after write_timeout_ms
and release their connection slots. Other clients must remain serviceable.
