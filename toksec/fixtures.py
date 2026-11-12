import asyncio
import json
import os
import subprocess
from pathlib import Path

from toksec.specification import configuration
from toksec.wire import payload


def create(directory, level):
    directory = Path(directory)
    root = directory / 'www'
    for sub in ('data', 'text', 'directory', 'assets', 'beta'):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for name, body in {'hello.txt': b'hello toksec\n', 'empty': b'', 'large': payload(2 * 1024 * 1024),
                       'space name.txt': b'space\n', 'directory/index.html': b'<p>index</p>\n',
                       'assets/item.txt': b'asset\n', 'beta/hello.txt': b'beta toksec\n'}.items():
        (root / name).write_bytes(body)
    for size in (4096, 65536):
        (root / 'data' / str(size)).write_bytes(payload(size))
        (root / 'text' / (str(size) + '.txt')).write_bytes(payload(size, True))
    (directory / 'secret').write_bytes(b'outside root secret')
    (root / 'escape').symlink_to('/fixtures/secret')
    (root / 'inside-link').symlink_to('hello.txt')
    os.mkfifo(root / 'pipe')
    (directory / 'server.conf').write_text(''.join(f'{k}={v}\n' for k, v in configuration(level).items()))
    if level == 5:
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=alpha.test', '-addext', 'subjectAltName=DNS:alpha.test,DNS:beta.test',
                        '-keyout', str(directory / 'key.pem'), '-out', str(directory / 'cert.pem')],
                       check=True, capture_output=True, timeout=10)


async def upstreams(ready):
    counter = 0
    aborted_posts = 0

    async def handle(reader, writer, identity):
        nonlocal counter, aborted_posts
        try:
            while True:
                raw = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
                lines = raw[:-4].split(b'\r\n')
                method, target, _ = lines[0].split(b' ')
                headers = dict(line.lower().split(b':', 1) for line in lines[1:])
                length = int(headers.get(b'content-length', b'0').strip())
                if not 0 <= length <= 1048576:
                    raise ValueError('fixture upload limit exceeded')
                body = await reader.readexactly(length)
                counter += 1
                path = target.decode()
                extra = b''
                if path.startswith('/slow'):
                    await asyncio.sleep(2)
                if path == '/abort-post' and method == b'POST':
                    aborted_posts += 1
                    break
                if path == '/abort-count':
                    content = str(aborted_posts).encode()
                elif path.startswith('/data/'):
                    size = int(path.split('/')[-1])
                    if size not in (4096, 65536):
                        raise ValueError('unknown fixture size')
                    content = payload(size)
                elif path.startswith('/id'):
                    content = str(identity).encode()
                elif path.startswith('/connection'):
                    content = f'{identity}:{writer.get_extra_info("peername")[1]}'.encode()
                elif path.startswith('/headers'):
                    content = json.dumps({k.decode(): v.decode().strip() for k, v in headers.items()}).encode()
                    extra = b'Connection: keep-alive, X-Upstream-Hop\r\nX-Upstream-Hop: remove\r\n'
                elif path.startswith('/counter'):
                    content = f'{identity}:{counter}'.encode()
                    extra = b'Cache-Control: public,max-age=60\r\n'
                    if 'no_store=1' in path:
                        extra = b'Cache-Control: no-store\r\n'
                    if 'cookie=1' in path:
                        extra += b'Set-Cookie: test=value\r\n'
                    if 'vary_star=1' in path:
                        extra += b'Vary: *\r\n'
                    if 'vary_other=1' in path:
                        extra += b'Vary: User-Agent\r\n'
                    if 'vary_encoding=1' in path:
                        extra += b'Vary: Accept-Encoding\r\n'
                    if 'private=1' in path:
                        extra = b'Cache-Control: private,max-age=60\r\n'
                elif path.startswith('/oversize'):
                    content = payload(1048577)
                elif path.startswith('/chunked'):
                    writer.write(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n10\r\nchunked response\r\n0\r\n\r\n')
                    await writer.drain()
                    continue
                elif path.startswith('/bad-framing'):
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\nxx')
                    await writer.drain()
                    break
                else:
                    content = method + b' ' + target + b'\n' + body
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(content)).encode() + b'\r\n' + extra + b'\r\n')
                if method != b'HEAD':
                    writer.write(content)
                await writer.drain()
        except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    servers = []
    for identity, port in enumerate((8081, 8082)):
        servers.append(await asyncio.start_server(lambda r, w, n=identity: handle(r, w, n), '127.0.0.1', port))
    Path(ready).write_text('ready')
    try:
        await asyncio.Event().wait()
    finally:
        for server in servers:
            server.close()


if __name__ == '__main__':
    import sys
    asyncio.run(upstreams(sys.argv[1]))
