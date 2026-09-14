import io
import socket
from pathlib import Path

import pytest

from app import network


def public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]


class FakeCurl:
    def __init__(self, command, *, body=b'ok', status='200 OK', location=None, **kwargs):
        self.stdout = io.BytesIO(body)
        self.returncode = 0
        self.killed = False
        headers = Path(command[command.index('--dump-header') + 1])
        headers.write_text('HTTP/2 ' + status + '\n' + ('Location: ' + location + '\n' if location else ''))
        assert '--resolve' in command
        assert '--noproxy' in command
        assert '--location' not in command
        assert '--insecure' not in command

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def communicate(self, **kwargs):
        return b'', b''

    def kill(self):
        self.killed = True


def test_redirect_to_private_address_is_never_fetched(monkeypatch):
    monkeypatch.setattr(network.socket, 'getaddrinfo', public_dns)
    calls = []
    def curl(command, **kwargs):
        calls.append(command)
        return FakeCurl(command, status='302 Found', location='http://127.0.0.1/secret', **kwargs)
    monkeypatch.setattr(network.subprocess, 'Popen', curl)
    with pytest.raises(ValueError, match='Private'):
        network.fetch('https://example.com')
    assert len(calls) == 1


def test_decompressed_response_is_bounded_and_killed(monkeypatch):
    monkeypatch.setattr(network.socket, 'getaddrinfo', public_dns)
    monkeypatch.setattr(network, 'MAX_BYTES', 5)
    processes = []
    def curl(command, **kwargs):
        result = FakeCurl(command, body=b'1234567890', **kwargs)
        processes.append(result)
        return result
    monkeypatch.setattr(network.subprocess, 'Popen', curl)
    with pytest.raises(ValueError, match='too large'):
        network.fetch('https://example.com')
    assert processes[0].killed
    assert processes[0].stdout.tell() == 6


def test_mixed_public_private_dns_rejected_before_curl(monkeypatch):
    monkeypatch.setattr(network.socket, 'getaddrinfo', lambda *a, **k: public_dns() + [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.2', 443))])
    with pytest.raises(ValueError, match='DNS'):
        network.fetch('https://example.com')
