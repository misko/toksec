# Stage 1: static GET server

Implement GET over HTTP/1.0 and HTTP/1.1 origin-form requests. Respond once and
close with Connection: close. The shared HTTP file-serving requirements apply.
The absolute header deadline starts at accept, including a client that sends no
bytes. Close at header_timeout_ms even if bytes keep arriving. A 408 response is
optional. Concurrency is optional for API acceptance, but performance is evaluated
at 256 and 4096 clients.
