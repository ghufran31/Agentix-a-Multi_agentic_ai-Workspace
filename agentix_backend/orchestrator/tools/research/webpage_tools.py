import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import urljoin, urlsplit

from pydantic import Field

from orchestrator.agents.research.schemas import ResearchModel, Source


class PageInput(ResearchModel):
    url: str = Field(max_length=2048)


class PageText(HTMLParser):
    ignored = {'script', 'style', 'nav', 'footer', 'header', 'svg', 'aside', 'noscript'}

    def __init__(self):
        super().__init__()
        self.hidden = []
        self.in_title = False
        self.title = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in self.ignored:
            self.hidden.append(tag)
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if not self.hidden:
            (self.title if self.in_title else self.text).append(data)


def public_destination(url):
    if len(url) > 2048 or any(ord(char) <= 32 or char == '\\' for char in url):
        raise ValueError('Malformed URL')
    parts = urlsplit(url)
    if (parts.scheme not in {'http', 'https'} or not parts.hostname
            or parts.username is not None or parts.password is not None):
        raise ValueError('Unsupported URL')
    port = 443 if parts.scheme == 'https' else 80
    if parts.port not in (None, port) or '%' in parts.hostname:
        raise ValueError('Unsupported destination')
    host = parts.hostname.encode('idna').decode('ascii')
    if '.' not in host and ':' not in host:
        raise ValueError('Public host required')
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = [ipaddress.ip_address(item[4][0]) for item in answers]
    if not addresses or any(not ip.is_global or ip.is_multicast for ip in addresses):
        raise ValueError('Nonpublic destination')
    return parts, host, port, str(addresses[0])


def read_webpage(url):
    deadline = monotonic() + 8
    try:
        for _ in range(4):
            parts, host, port, address = public_destination(url)
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            connection = http.client.HTTPConnection(host, port, timeout=remaining)
            response = None
            try:
                # Connect to the checked address without another hostname lookup.
                connection.sock = socket.create_connection((address, port), remaining)
                if parts.scheme == 'https':
                    connection.sock = ssl.create_default_context().wrap_socket(
                        connection.sock, server_hostname=host)
                transport = connection.sock
                path = parts.path or '/'
                if parts.query:
                    path += '?' + parts.query
                connection.request('GET', path, headers={'Accept-Encoding': 'identity',
                                                        'User-Agent': 'AgentixResearch/1.0'})
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader('Location')
                    if not location:
                        break
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    return {'error': f'http_{response.status}', 'sources': []}
                if (response.headers.get_content_type() not in {'text/html', 'text/plain'}
                        or response.getheader('Content-Encoding', 'identity') != 'identity'):
                    return {'error': 'unsupported_content', 'sources': []}
                data = bytearray()
                while len(data) < 262144:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    transport.settimeout(remaining)
                    chunk = response.read1(min(8192, 262144 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                decoded = data.decode('utf-8', errors='replace')
                parser = PageText()
                if response.headers.get_content_type() == 'text/html':
                    parser.feed(decoded)
                else:
                    parser.text.append(decoded)
                excerpt = ' '.join(' '.join(parser.text).split())[:2800]
                if not excerpt:
                    return {'error': 'empty_page', 'sources': []}
                source = Source(title=' '.join(' '.join(parser.title).split())[:200] or host,
                                url=url, excerpt=excerpt, provider='webpage')
                return {'sources': [source.model_dump(mode='json')]}
            finally:
                if response is not None:
                    response.close()
                connection.close()
        return {'error': 'redirect_limit', 'sources': []}
    except TimeoutError:
        return {'error': 'page_timeout', 'sources': []}
    except (ValueError, OSError, http.client.HTTPException):
        return {'error': 'unsafe_or_unreachable_url', 'sources': []}
