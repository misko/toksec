from toksec.stages import module as stage_module
import time
import os
import signal
from pathlib import Path
from toksec.wire import Wire, request
from toksec.check_types import Case

class Context:
    def __init__(self, level, fixtures, server_pid, upstreams=None):
        self.level = level
        self.fixtures = Path(fixtures)
        self.pid = server_pid
        self.upstreams = upstreams
        self.original_config = (self.fixtures / 'server.conf').read_text()

    def exchange(self, raw=None, *, head=False, tls=False, server_name='alpha.test'):
        with Wire(8443 if tls else 8080, tls=tls, host=server_name) as wire:
            wire.send(raw or request())
            result = wire.read(head=head)
            if self.level == 1:
                assert result.header('connection', '').lower() == 'close'
                assert wire.stream.read(1) == b'', 'connection did not close'
            return result

    def get(self, path='/hello.txt', status=200, body=None, **kwargs):
        result = self.exchange(request(path, **kwargs), head=kwargs.get('method') == 'HEAD')
        assert result.status == status, f'{path}: expected {status}, got {result.status}'
        if body is not None:
            assert result.body == body, 'incorrect body bytes'
        return result

    def reload(self, changes=None, invalid=False):
        values = dict(line.split('=', 1) for line in self.original_config.splitlines() if line)
        values.update(changes or {})
        data = '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n'
        if invalid:
            data += 'unrecognized=true\n'
        (self.fixtures / 'server.conf').write_text(data)
        os.kill(self.pid, signal.SIGHUP)
        time.sleep(0.15)


def cases_for(level):
    return list(stage_module(level, 'api').CASES)


def configured_cases(level):
    if level >= 2:
        from toksec.stages import module as stage_module
        CONFIGURED_CASES = stage_module(2, 'api').CONFIGURED_CASES
        return CONFIGURED_CASES
    return []


EXTERNAL_CASES = [Case('configuration', 1, 'Invalid, duplicate, missing and unknown config values exit nonzero before serving.', None)]


def run_checks(context, selected=None):
    results = []
    for check in selected if selected is not None else cases_for(context.level):
        if check.minimum > context.level:
            continue
        started = time.monotonic()
        try:
            check.execute(context)
            results.append({'id': check.id, 'passed': True, 'seconds': time.monotonic() - started})
        except Exception as error:
            results.append({'id': check.id, 'passed': False, 'seconds': time.monotonic() - started,
                            'error': f'{type(error).__name__}: {error}'[:1000]})
    return {'cases': results, 'passed': all(r['passed'] for r in results)}
