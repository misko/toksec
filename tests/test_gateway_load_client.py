import asyncio
import json
import time
import unittest
from dataclasses import asdict

from stages.common.grading.gateway_fixture import binary
from stages.common.grading.performance import Workload
from toksec import benchmark


class GatewayLoadClientTests(unittest.TestCase):
    async def exercise(self, workload, variant, native):
        spec = asdict(workload)
        raw, expected = benchmark.request_bytes(spec)
        observed = []
        active = set()

        async def serve(reader, writer):
            active.add(writer)
            try:
                while await reader.readexactly(len(raw)) == raw:
                    observed.append(True)
                    if variant == 'late':
                        await asyncio.sleep(.2)
                    status = '403 Denied' if variant == 'refused' else '200 OK'
                    reply = f'HTTP/1.1 {status}\r\nContent-Length: {len(expected)}\r\n'
                    if variant == 'duplicate':
                        reply += f'Content-Length: {len(expected)}\r\n'
                    if variant == 'close':
                        reply += 'Connection: close\r\n'
                    body = b'x' * len(expected) if variant == 'wrong-body' else expected
                    writer.write(reply[:9].encode())
                    await writer.drain()
                    await asyncio.sleep(.001)
                    writer.write(reply[9:].encode() + b'\r\n' + body)
                    await writer.drain()
                    if variant == 'close':
                        break
            except (OSError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                active.discard(writer)

        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        spec['target_port'] = port
        async with server:
            start = time.monotonic() + .03
            if native:
                times = (start, workload.warmup_seconds, workload.seconds, workload.timeout_seconds)
                proc = await asyncio.create_subprocess_exec(
                    str(binary('client')), '2', str(port), *[str(round(t * 1e9)) for t in times],
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                output, err = await proc.communicate(f'{len(raw)} {len(expected)}\n'.encode() + raw + expected)
                self.assertEqual(proc.returncode, 0, err)
                result = json.loads(output)
            else:
                result = await benchmark.load(spec, 2, start)
        for writer in list(active):
            writer.close()
        self.assertTrue(observed)
        self.assertEqual(result['attempts'], result['failures'] + result['successes'])
        self.assertEqual(sum(result['failure_classes'].values()), result['failures'])
        self.assertEqual(sum(result['histogram']), result['successes'])
        self.assertEqual(result['payload_bytes'], result['completed_in_window'] * len(expected))
        self.assertEqual(result['clients_started'], 2)
        return result

    def test_identical_get_and_upload_with_fragmented_headers_and_reconnect(self):
        for stage in (14, 16):
            workload = Workload(f'gateway-{stage}-4096-256', 2, '/gateway/data/4096', 4096,
                                persistent=True, warmup_seconds=.02, seconds=.08, timeout_seconds=.2)
            for native in (False, True):
                with self.subTest(stage=stage, native=native):
                    result = asyncio.run(self.exercise(workload, 'close' if stage == 16 else 'ok', native))
                    self.assertEqual(result['failures'], 0)
                    self.assertGreater(result['completed_in_window'], 0)

    def test_wrong_body_framing_status_and_timeout_have_no_goodput(self):
        workload = Workload('gateway-14-public-4096-256', 2, '/data/4096', 4096,
                            persistent=True, warmup_seconds=0, seconds=.08, timeout_seconds=.06)
        for native in (False, True):
            for variant, reason in [('wrong-body', 'body_mismatch'), ('duplicate', 'protocol'),
                                    ('refused', 'http_403'), ('late', 'timeout_response')]:
                with self.subTest(native=native, variant=variant):
                    result = asyncio.run(self.exercise(workload, variant, native))
                    self.assertEqual(result['successes'], 0)
                    self.assertGreater(result['failure_classes'][reason], 0)

    def test_calibration_origin_uses_same_bytes_on_explicit_upload_path(self):
        spec = asdict(Workload('gateway-16-65536-4096', 4096, '/gateway/data/65536', 65536, persistent=True))
        gateway, expected = benchmark.request_bytes(spec)
        origin, origin_expected = benchmark.request_bytes({**spec, 'request_path': '/upload'})
        self.assertTrue(gateway.startswith(b'POST /gateway/upload HTTP/1.1\r\n'))
        self.assertEqual(origin, gateway.replace(b'/gateway/upload', b'/upload', 1))
        self.assertEqual(origin_expected, expected)
        self.assertEqual(gateway.split(b'\r\n\r\n', 1)[1], expected)
