"""Independent gateway checks. Use parent-only observations for downstream effects."""
import time
from pathlib import Path

from toksec.check_types import Case
from toksec.wire import Wire, request
from stages.common.grading.gateway_origin import control


def snapshot(c, **policy):
    return control(c.upstreams, **policy)


def fetch(c, target='/doc', token='reader', **kwargs):
    headers = {'Authorization': 'Bearer '+token, **kwargs.pop('headers', {})}
    return c.get('/gateway'+target, headers=headers, **kwargs)


def authorization(c):
    try:
        for decision, status in [(200,200),(401,401),(403,403),(500,503),(504,503)]:
            before = snapshot(c, reader=decision)
            fetch(c, status=status)
            after = snapshot(c)
            assert after['auth'] == before.get('auth',0)+1
            if decision != 200:
                assert after.get('origin',0) == before.get('origin',0)
            assert not after.get('forwarded_credentials')
            c.get(body=b'hello toksec\n')
    finally:
        snapshot(c, reader=200)


def cache_scope(c):
    for host,variant in [('alpha.test','en'),('beta.test','en'),('alpha.test','fr')]:
        path = '/doc?cache-scope'
        before = snapshot(c).get('origin',0)
        for _ in range(2):
            fetch(c,path,host=host,headers={'Accept-Language':variant},body=f'{host}|{path}|{variant}'.encode())
        assert snapshot(c)['origin'] == before+1
    before = snapshot(c)['origin']
    for _ in range(2):
        fetch(c,'/doc?private')
    assert snapshot(c)['origin'] == before+2


def revalidate(c):
    body = fetch(c,'/doc?validator').body
    before = snapshot(c)
    time.sleep(.8)
    assert fetch(c,'/doc?validator').body == body
    assert snapshot(c)['revalidated'] == before.get('revalidated',0)+1


def revocation(c):
    path = '/doc?revocation'
    body = fetch(c,path).body
    before = snapshot(c,reader=403)
    try:
        fetch(c,path,status=403)
        fetch(c,path,token='other',body=body)
        after = snapshot(c)
        assert after['auth'] == before['auth']+2
        assert after['origin'] == before['origin']
    finally:
        snapshot(c,reader=200)


def admission(c):
    c.reload({'refill_ms':'3000','global_burst':'4','client_burst':'2'})
    try:
        before = snapshot(c)
        for identity, status in [('192.0.2.1',200)]*2+[('192.0.2.1',429),('192.0.2.2',200),('192.0.2.2',200),('192.0.2.3',429)]:
            c.get('/gateway/admission',headers={'X-Real-IP':identity},status=status)
        c.get('/health',body=b'ok\n')
        assert snapshot(c)['origin'] == before.get('origin',0)+4
        time.sleep(3.1)
        c.get('/gateway/admission',headers={'X-Real-IP':'192.0.2.1'})
        c.reload({'trusted_peer':'192.0.2.100','client_burst':'1'})
        c.get('/gateway/admission',headers={'X-Real-IP':'192.0.2.1'})
        c.get('/gateway/admission',headers={'X-Real-IP':'192.0.2.2'},status=429)
    finally:
        c.reload()


def mtls(c):
    c.get('/gateway/identity',body=b'/identity')
    assert snapshot(c).get('cert:client',0)>0
    try:
        c.reload({'tls_name':'wrong.test'})
        before = snapshot(c)['origin']
        c.get('/gateway/identity',status=502)
        assert snapshot(c)['origin'] == before
        c.reload({'tls_key':'/fixtures/rotated.key','tls_cert':'/fixtures/rotated.pem'})
        c.get('/gateway/identity',body=b'/identity')
        before = snapshot(c)['cert:rotated']
        c.reload({'tls_key':'/fixtures/missing'})
        c.get('/gateway/identity',body=b'/identity')
        assert snapshot(c)['cert:rotated'] == before+1
    finally:
        c.reload()


def upload(c):
    def post(body):
        return c.exchange(request('/gateway/upload', method='POST',
                                  headers={'Content-Length':str(len(body))}, body=body))
    data = bytes(range(256))*512
    before = snapshot(c).get('origin',0)
    response = post(data)
    assert (response.status,response.body)==(200,data)
    assert post(data+b'x').status==413
    assert c.exchange(request('/gateway/upload',method='POST')).status==411
    assert snapshot(c)['origin']==before+1


def upload_limits(c):
    origin_before = snapshot(c).get('origin',0)
    def partial(wire,host,length):
        wire.send(request('/gateway/upload',method='POST',host=host,headers={'Content-Length':str(length)},body=b'x'*2048))
    with Wire() as a, Wire() as b:
        partial(a,'alpha.test',131072)
        time.sleep(.05)
        with Wire() as rejected:
            partial(rejected,'alpha.test',131072)
            assert rejected.read().status==429
        partial(b,'beta.test',131072)
        time.sleep(.05)
        with Wire() as rejected:
            partial(rejected,'other.test',131072)
            assert rejected.read().status==429
        c.get('/health',body=b'ok\n')
    time.sleep(.15)
    assert snapshot(c).get('origin',0)==origin_before
    assert not any((Path(f'/proc/{c.pid}/root/tmp/spool')).iterdir())
    with Wire() as stalled:
        partial(stalled,'alpha.test',131072)
        time.sleep(.85)
        assert snapshot(c).get('origin',0)==origin_before
        upload(c)


def policy_cases(stage):
    selected = {11:[authorization],12:[cache_scope,revalidate],13:[authorization,cache_scope,revalidate,revocation],
                14:[admission],15:[mtls],16:[upload,upload_limits]}[stage]
    return [Case(fn.__name__.replace('_','-'),stage,fn.__name__.replace('_',' '),fn) for fn in selected]
