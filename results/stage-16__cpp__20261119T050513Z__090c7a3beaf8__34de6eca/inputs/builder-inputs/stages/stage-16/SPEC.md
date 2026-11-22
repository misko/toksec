# Stage 16: Disk-backed upload gateway

Independent from-scratch assignment. POST /gateway/upload requires exactly one decimal Content-Length, responds 411 when absent, 400 on malformed framing, and 413 when greater than upload_bytes.
