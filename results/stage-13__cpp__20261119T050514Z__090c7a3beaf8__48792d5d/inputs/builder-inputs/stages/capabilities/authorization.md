# Authorization

Before every GET or HEAD under /gateway/, issue GET /authorize to auth_address with the original Host, request target in X-Original-URI and original Authorization if present. No body. Any 2xx permits forwarding. Return 401 or 403 unchanged for a denial and 503 for a service error, timeout or missing reply. On any refusal, do not contact the origin. Local routes remain available. Never cache authorization decisions or send bearer credentials to the content origin. The public benchmark credential is Bearer reader.
