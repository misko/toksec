"""Parent-owned HTTP fixtures. Control traffic uses a host-only Unix socket."""
import asyncio
import json
import socket
import ssl
import subprocess
import sys
from collections import Counter
from pathlib import Path

from toksec.wire import payload


def issue_certificates(private, public):
    """Generate short-lived fixture identities; only client credentials enter the sandbox."""
    def openssl(*args):
        subprocess.run(['openssl', *map(str, args)], cwd=private, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    openssl('req', '-new', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
            '-nodes', '-days', '2', '-subj', '/CN=Toksec fixture CA', '-addext',
            'basicConstraints=critical,CA:TRUE', '-keyout', 'ca.key', '-out', public/'ca.pem')
    for name, usage in [('origin.test', 'serverAuth'), ('client', 'clientAuth'), ('rotated', 'clientAuth')]:
        key = (private if usage == 'serverAuth' else public) / (name + '.key')
        cert = key.with_suffix('.pem') if usage == 'clientAuth' else private/'origin.pem'
        openssl('req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
                '-nodes', '-subj', '/CN='+name, '-keyout', key, '-out', 'request.csr')
        (private/'extensions').write_text(f'extendedKeyUsage={usage}\nsubjectAltName=DNS:{name}\n')
        openssl('x509', '-req', '-days', '2', '-in', 'request.csr', '-CA', public/'ca.pem',
                '-CAkey', 'ca.key', '-set_serial', str(10+len(name)), '-extfile', 'extensions', '-out', cert)


def control(directory, **values):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(2)
        sock.connect(str(Path(directory)/'control'))
        sock.sendall(json.dumps(values).encode()+b'\n')
        return json.loads(sock.makefile('rb').readline())


async def serve(stage, public, private):
    counts = Counter()
    policy = {'reader': 200, 'other': 200}
    async def admin(reader, writer):
        values = json.loads(await reader.readline())
        policy.update(values)
        writer.write(json.dumps(dict(counts)).encode()+b'\n')
        await writer.drain()
        writer.close()

    async def handle(reader, writer, auth):
        try:
            while True:
                block = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 3)
                line, *fields = block[:-4].split(b'\r\n')
                method, target, _ = line.decode('ascii').split()
                headers = {k.lower().strip(): v.strip() for k,v in
                           (line.decode('latin1').split(':',1) for line in fields)}
                length = int(headers.get('content-length', 0))
                if length < 0 or length > 1048576:
                    break
                body = await asyncio.wait_for(reader.readexactly(length), 3)
                extra = ''
                code = 200
                if auth:
                    counts['auth'] += 1
                    credential = headers.get('authorization', '').removeprefix('Bearer ')
                    code = policy.get(credential, 403) if (method == 'GET' and target == '/authorize' and headers.get('host') and headers.get('x-original-uri','').startswith('/gateway/') and not body) else 404
                    if code == 504:
                        await asyncio.sleep(1)
                    body = b''
                else:
                    counts['origin'] += 1
                    if 'authorization' in headers: counts['forwarded_credentials'] += 1
                    if writer.get_extra_info('ssl_object'):
                        cert = writer.get_extra_info('peercert')
                        counts['cert:'+cert['subject'][0][0][1]] += 1
                    if target.startswith('/data/'):
                        size = int(target.split('/')[-1])
                        if size not in (4096,65536): break
                        body = payload(size)
                        extra = 'Cache-Control: public,max-age=60\r\n'
                    elif target == '/upload' and method == 'POST':
                        pass
                    elif target.startswith('/doc'):
                        extra = 'ETag: "one"\r\nVary: Accept-Language\r\n'
                        extra += 'Cache-Control: '+('private' if 'private' in target else 'public,max-age=60')+'\r\n'
                        if headers.get('if-none-match') == '"one"':
                            counts['revalidated'] += 1
                            code,body = 304,b''
                        else:
                            body = '|'.join((headers.get('host',''),target,headers.get('accept-language',''))).encode()
                    else:
                        body = target.encode()
                writer.write(f'HTTP/1.1 {code} Fixture\r\n{extra}Content-Length: {len(body)}\r\n\r\n'.encode())
                if method != 'HEAD': writer.write(body)
                await writer.drain()
        except (OSError, ValueError, EOFError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            writer.close()
    tls = None
    if stage == 15:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(private/'origin.pem', private/'origin.test.key')
        tls.load_verify_locations(public/'ca.pem')
        tls.verify_mode = ssl.CERT_REQUIRED
    async with await asyncio.start_server(lambda r,w: handle(r,w,False),'127.0.0.1',8081,ssl=tls), await asyncio.start_server(lambda r,w: handle(r,w,True),'127.0.0.1',8082), await asyncio.start_unix_server(admin,private/'control'):
        (public/'upstream.ready').touch()
        await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(serve(int(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3])))
