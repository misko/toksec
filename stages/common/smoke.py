from toksec.check_types import Case
from toksec.wire import Wire, request


def get(c):
    with Wire() as wire:
        wire.send(request('/hello.txt'))
        response = wire.read()
        assert response.status == 200
        assert response.body == b'hello toksec\n'
        assert response.header('content-length') == str(len(response.body))
        assert response.header('connection', '').lower() == 'close'
        assert wire.stream.read(1) == b''


def head(c):
    with Wire() as wire:
        wire.send(request('/hello.txt', method='HEAD'))
        response = wire.read(head=True)
        assert response.status == 200
        assert response.header('content-length') == str(len(b'hello toksec\n'))
        assert wire.stream.read(1) == b''


def persistent(c):
    with Wire() as wire:
        for close in (False, True):
            wire.send(request('/hello.txt', close=close))
            response = wire.read()
            assert response.status == 200 and response.body == b'hello toksec\n'
        assert wire.stream.read(1) == b''


def cases(level):
    selected = [Case('bootstrap', 1, 'Ordinary GET of an existing small ASCII file: 200, exact bytes, Content-Length and close.', get)]
    if level >= 2:
        selected += [Case('smoke-head', 2, 'Ordinary HEAD of the same existing file: 200, representation length and no body.', head),
                     Case('smoke-persistent', 2, 'Two ordinary sequential GETs on one persistent connection.', persistent)]
    return selected
