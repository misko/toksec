# Tenant Cache

Cache successful public GETs under /gateway/ across requests for at most cache_ttl_ms, with bounded total body bytes cache_bytes. Isolate Host, complete path/query and Accept-Language variants. Never store private, no-store, Set-Cookie or unsupported Vary responses. On expiry, revalidate an ETag with If-None-Match. On 304 reuse the exact stored body and refresh its TTL. On a new 200 replace the entry. Concurrent requests must never cross host boundaries. Forward Accept-Language to the origin.
