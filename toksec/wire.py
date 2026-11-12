import socket
import ssl
from dataclasses import dataclass


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def header(self, name, default=None):
        values = self.headers.get(name.lower(), [])
        if len(values) > 1:
            raise AssertionError('duplicate ' + name)
        return values[0] if values else default


class Wire:
    def __init__(self, port=8080, tls=False, timeout=3, host='alpha.test'):
        sock = socket.create_connection(('127.0.0.1', port), timeout)
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            sock = context.wrap_socket(sock, server_hostname=host)
        self.socket = sock
        self.stream = sock.makefile('rb')

    def close(self):
        self.stream.close()
        self.socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, raw):
        self.socket.sendall(raw)

    def read(self, head=False):
        line = self.stream.readline(8193)
        parts = line.rstrip(b'\r\n').split(b' ', 2)
        assert line.endswith(b'\r\n') and len(parts) == 3 and parts[0] in (b'HTTP/1.0', b'HTTP/1.1'), 'invalid status line'
        status = int(parts[1])
        headers = {}
        total = len(line)
        while True:
            line = self.stream.readline(8193)
            total += len(line)
            assert line.endswith(b'\r\n') and total <= 65536, 'invalid response headers'
            if line == b'\r\n':
                break
            name, value = line[:-2].split(b':', 1)
            headers.setdefault(name.decode('ascii').lower(), []).append(value.strip().decode('latin1'))
        result = Response(status, headers, b'')
        length = result.header('content-length')
        assert length is not None and length.isascii() and length.isdecimal(), 'Content-Length required'
        assert result.header('transfer-encoding') is None, 'downstream transfer coding forbidden'
        length = int(length)
        assert 0 <= length <= 8 * 1024 * 1024, 'response body too large'
        if not head and status not in (204, 304):
            result.body = self.stream.read(length)
            assert len(result.body) == length, 'truncated response'
        return result


def request(path='/hello.txt', method='GET', headers=None, body=b'', close=True, host='alpha.test'):
    fields = [('Host', host)] if host is not None else []
    if close:
        fields.append(('Connection', 'close'))
    fields.extend((headers or {}).items())
    return (f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in fields) + '\r\n').encode() + body


def payload(size, text=False):
    pattern = b'toksec public workload\n' if text else bytes(range(256))
    return (pattern * (size // len(pattern) + 1))[:size]
