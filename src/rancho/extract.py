"""Contained fetching and extraction of untrusted web content.

The fetcher treats every target as hostile: it vets resolved addresses against
private/loopback/reserved ranges, pins the connection to a vetted IP so a name
cannot rebind to an internal address between check and connect, bounds redirects
and response size, and converts HTML to bounded markdown without executing page
script. A fetch that cannot complete safely raises a typed error; it never
fabricates content.
"""

from __future__ import annotations

import ipaddress
import random
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

_MAX_REDIRECTS = 3
_MAX_CONTENT_BYTES = 2_097_152
_MAX_MARKDOWN_CHARS = 200_000
_FETCH_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0)
_ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_STRIP_TAGS = (
    "script",
    "style",
    "form",
    "iframe",
    "nav",
    "header",
    "footer",
    "aside",
    "noscript",
    "svg",
    "template",
)
# Honest, rotating agents; no ambient credentials are ever attached.
_USER_AGENTS = (
    "Mozilla/5.0 (compatible; RanchoResearcho/1.0; +https://github.com/joeldg/rancho-researcho)",
    "RanchoResearcho/1.0 (+https://github.com/joeldg/rancho-researcho)",
)

Resolver = Callable[[str, int], list[tuple]]


class ContentUnavailableError(Exception):
    """Raised when a URL cannot be fetched and extracted safely."""


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
@dataclass
class FetchedPage:
    """The bounded markdown evidence extracted from a safely retrieved URL."""

    final_url: str
    markdown: str


def _default_resolver(host: str, port: int) -> list[tuple]:
    """Resolve a host to candidate TCP endpoints."""
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def _is_blocked_address(ip_text: str) -> bool:
    """Return True for any address Rancho must never connect to."""
    try:
        address = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def _resolve_and_vet(host: str, port: int, resolver: Resolver) -> list[str]:
    """Resolve a host and refuse if it is unresolvable or any IP is blocked."""
    try:
        infos = resolver(host, port)
    except OSError as error:
        raise ContentUnavailableError from error
    addresses = {info[4][0] for info in infos if info and info[4]}
    if not addresses:
        raise ContentUnavailableError
    for address in addresses:
        if _is_blocked_address(address):
            raise ContentUnavailableError
    return sorted(addresses)


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
class WebContentFetcher:
    """Fetch untrusted URLs under strict SSRF and resource containment."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        resolver: Resolver = _default_resolver,
    ) -> None:
        self._client = client
        self._resolver = resolver

    # @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
    def fetch(self, url: str) -> FetchedPage:
        """Return bounded markdown for a URL or raise ContentUnavailableError."""
        client = self._client or httpx.Client(follow_redirects=False)
        owns_client = self._client is None
        try:
            try:
                return self._follow(url, client)
            except ContentUnavailableError:
                raise
            except (httpx.HTTPError, OSError, ValueError) as error:
                raise ContentUnavailableError from error
        finally:
            if owns_client:
                client.close()

    def _follow(self, url: str, client: httpx.Client) -> FetchedPage:
        current = url
        seen: set[str] = set()
        for _ in range(_MAX_REDIRECTS + 1):
            if current in seen:
                raise ContentUnavailableError  # redirect loop
            seen.add(current)
            parsed = urlsplit(current)
            if parsed.scheme not in _DEFAULT_PORTS or not parsed.hostname:
                raise ContentUnavailableError
            port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
            # Re-vet the address on every hop, then pin to a vetted IP.
            vetted = _resolve_and_vet(parsed.hostname, port, self._resolver)
            redirect, page = self._fetch_once(current, parsed, vetted[0], port, client)
            if page is not None:
                return page
            current = urljoin(current, redirect)
        raise ContentUnavailableError  # too many redirects

    # @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
    def _fetch_once(
        self,
        current: str,
        parsed,
        ip: str,
        port: int,
        client: httpx.Client,
    ) -> tuple[str | None, FetchedPage | None]:
        """Perform one pinned, bounded request; return a redirect or a page."""
        netloc = f"[{ip}]" if ":" in ip else ip
        target = urlunsplit(
            (parsed.scheme, f"{netloc}:{port}", parsed.path or "/", parsed.query, "")
        )
        host_header = (
            parsed.hostname
            if port == _DEFAULT_PORTS[parsed.scheme]
            else f"{parsed.hostname}:{port}"
        )
        headers = {
            "Host": host_header,
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
        }
        with client.stream(
            "GET",
            target,
            headers=headers,
            extensions={"sni_hostname": parsed.hostname},
            follow_redirects=False,
            timeout=_FETCH_TIMEOUT,
        ) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ContentUnavailableError
                return location, None
            if not response.is_success:
                raise ContentUnavailableError
            media_type = (
                response.headers.get("content-type", "")
                .split(";", maxsplit=1)[0]
                .strip()
                .lower()
            )
            if media_type not in _ALLOWED_CONTENT_TYPES:
                raise ContentUnavailableError
            declared = response.headers.get("content-length")
            if declared and int(declared) > _MAX_CONTENT_BYTES:
                raise ContentUnavailableError
            body = self._read_capped(response)
        html = body.decode(response.encoding or "utf-8", errors="replace")
        return None, FetchedPage(final_url=current, markdown=html_to_markdown(html))

    @staticmethod
    def _read_capped(response: httpx.Response) -> bytes:
        """Stream the body, refusing once the size cap is exceeded."""
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > _MAX_CONTENT_BYTES:
                raise ContentUnavailableError
            chunks.append(chunk)
        return b"".join(chunks)


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def html_to_markdown(html: str) -> str:
    """Convert HTML to bounded markdown, dropping script and chrome tags."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()
    root = soup.body or soup
    markdown = markdownify(str(root), heading_style="ATX", strip=["img"])
    return _collapse_blank_lines(markdown)[:_MAX_MARKDOWN_CHARS].strip()


def _collapse_blank_lines(text: str) -> str:
    """Reduce runs of blank lines to a single blank line."""
    result: list[str] = []
    blank = False
    for line in text.splitlines():
        if line.strip() == "":
            if not blank:
                result.append("")
            blank = True
        else:
            result.append(line)
            blank = False
    return "\n".join(result)
