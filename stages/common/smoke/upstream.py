"""Ordinary development traffic only. No held-out fault fixtures."""
import asyncio
from pathlib import Path
from toksec.wire import payload

async def upstreams(ready):
    count = 0
    async def handle(reader, writer):
        nonlocal count
        try:
            while True:
                raw = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
                method, path, _ = raw.split(b'\r\n', 1)[0].split(b' ')
                count += 1
                extra = b''
                if path.startswith((b'/data/', b'/cache/', b'/miss/')):
                    size = int(path.rsplit(b'/', 1)[1])
                    if size not in (4096, 65536):
                        raise ValueError('unknown ordinary workload')
                    body = payload(size)
                    if path.startswith(b'/cache/'):
                        extra = b'Cache-Control: public,max-age=60\r\n'
                    elif path.startswith(b'/miss/'):
                        extra = b'Cache-Control: public,max-age=0\r\n'
                elif path == b'/counter':
                    body = str(count).encode()
                    extra = b'Cache-Control: public,max-age=60\r\n'
                else:
                    body = method + b' ' + path + b'\n'
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n' + extra + b'\r\n')
                if method != b'HEAD':
                    writer.write(body)
                await writer.drain()
        except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
    servers = [await asyncio.start_server(handle, '127.0.0.1', port) for port in (8081, 8082)]
    Path(ready).write_text('ready')
    try:
        await asyncio.Event().wait()
    finally:
        for server in servers:
            server.close()

if __name__ == '__main__':
    import sys
    asyncio.run(upstreams(sys.argv[1]))
