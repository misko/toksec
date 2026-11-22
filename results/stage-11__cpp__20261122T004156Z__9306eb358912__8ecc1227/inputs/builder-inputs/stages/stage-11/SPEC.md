# Stage 11: Authorization gateway

Independent from-scratch assignment. Before every GET or HEAD to /gateway/, issue GET /authorize to auth_address with the original Host, request target in X-Original-URI and original Authorization if present.
