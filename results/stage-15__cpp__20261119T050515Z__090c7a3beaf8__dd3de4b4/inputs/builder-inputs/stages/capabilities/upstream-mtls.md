# Upstream Mtls

Connect to origin_address using OpenSSL TLS 1.2 or 1.3. Verify the origin chain against tls_ca and DNS identity tls_name; send SNI and authenticate with tls_cert and tls_key. Return 502 on any upstream TLS failure. Never forward plaintext to the origin. SIGHUP loads a new configuration and certificate generation atomically; reject missing or mismatched credentials and retain the last valid generation. The server listens for plaintext downstream. Only this stage permits OpenSSL.
