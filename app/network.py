"""Bounded public HTTP fetches. Curl validates TLS and pins validated DNS answers.

Every redirect is validated independently; no proxy or automatic curl redirects.
This also uses the host's certificate store on macOS.
"""
import ipaddress
import socket
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urljoin

MAX_BYTES = 4 * 1024 * 1024
USER_AGENT = 'DarmstadtLocal/0.1 (local community event calendar; occasional cached requests)'


def validate_url(url):
    if not isinstance(url, str) or len(url) > 3000 or any(ord(c) < 32 for c in url):
        raise ValueError('Invalid URL')
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Only public HTTP(S) URLs without credentials are supported')
    if p.port not in (None, 80 if p.scheme == 'http' else 443):
        raise ValueError('Nonstandard ports are not supported')
    host = p.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Private addresses are not allowed')
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return p
    if not addr.is_global:
        raise ValueError('Private addresses are not allowed')
    return p


def fetch(url):
    for _ in range(4):
        p = validate_url(url)
        port = p.port or (443 if p.scheme == 'https' else 80)
        answers = socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(a[4][0] for a in answers))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('DNS resolved to a private or unavailable address')
        ip = next((ip for ip in ips if ':' not in ip), ips[0])
        ip = f'[{ip}]' if ':' in ip else ip
        with tempfile.TemporaryDirectory(prefix='darmstadt-fetch-') as folder:
            headers = Path(folder) / 'headers'
            command = ['/usr/bin/curl', '--silent', '--show-error', '--compressed', '--noproxy', '*',
                       '--proto', '=http,https', '--connect-timeout', '8', '--max-time', '25',
                       '--max-filesize', str(MAX_BYTES), '--user-agent', USER_AGENT,
                       '--resolve', f'{p.hostname}:{port}:{ip}', '--dump-header', str(headers), '--url', url]
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
                # stdout is decompressed by curl. Read at most the limit + 1, then
                # kill immediately instead of first writing an oversized body.
                body = process.stdout.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    process.kill()
                    process.communicate()
                    raise ValueError('Response is too large')
                _, stderr = process.communicate(timeout=5)
                if process.returncode:
                    raise RuntimeError('Fetch failed: ' + stderr.decode(errors='replace')[:200])
            status_lines = [line for line in headers.read_text().splitlines() if line.startswith('HTTP/')]
            status = int(status_lines[-1].split()[1])
            if status in (301, 302, 303, 307, 308):
                location = next((line.split(':', 1)[1].strip() for line in headers.read_text().splitlines() if line.lower().startswith('location:')), None)
                if not location:
                    raise ValueError('Redirect lacks a destination')
                url = urljoin(url, location)
                continue
            if not 200 <= status < 300:
                raise RuntimeError(f'HTTP {status}')
            return body
    raise ValueError('Too many redirects')
