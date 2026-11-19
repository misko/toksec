#!/usr/bin/env python3
import sys
mode = sys.argv[1]; listen = int(sys.argv[2]); upstream = int(sys.argv[3]); path = sys.argv[4]
www = "/tmp/r12_www_D"
if mode == "nginx":
    open(path, "w").write("""worker_processes 1;
events { worker_connections 128; }
http {
  toksec_header_bytes 16384;
  toksec_header_deadline 2000;
  toksec_upstream_deadline 3000;
  upstream backend { server 127.0.0.1:%d; }
  server {
    listen 127.0.0.1:%d;
    server_name alpha.test;
    root %s/alpha;
    location /api/ { proxy_pass http://backend/api/; }
    location / { root %s/alpha; }
  }
}
""" % (upstream, listen, www, www))
else:
    open(path, "w").write("""listen=127.0.0.1:%d
root=%s/alpha
max_connections=64
header_bytes=16384
header_timeout_ms=2000
idle_timeout_ms=5000
write_timeout_ms=5000
max_requests=100
pipeline_depth=16
default_host=alpha.test
host_root=beta.test:%s/beta
alias=/alias:%s/alias
redirect=/go:/target
index=index.html
proxy_prefix=/api
upstreams=127.0.0.1:%d
upstream_timeout_ms=3000
body_bytes=1048576
cache_ttl_ms=0
cache_bytes=0
rate_per_second=0
rate_burst=100
drain_timeout_ms=1000
""" % (listen, www, www, www, upstream))
