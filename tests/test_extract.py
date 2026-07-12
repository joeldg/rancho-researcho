"""Contract tests for the contained web content fetcher and extractor."""

import socket

import httpx
import pytest

from rancho import extract
from rancho.extract import (
    ContentUnavailableError,
    WebContentFetcher,
    html_to_markdown,
)


def _resolver_for(mapping: dict[str, str], default: str = "93.184.216.34"):
    """Build a fake resolver mapping hostnames to a single IP."""

    def resolver(host: str, port: int) -> list[tuple]:
        ip = mapping.get(host, default)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    return resolver


def _ok_html(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/html"},
        text="<html><body><h1>Title</h1><p>Evidence.</p></body></html>",
    )


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
@pytest.mark.parametrize(
    "blocked_ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "169.254.169.254",  # link-local / cloud metadata
        "::1",  # ipv6 loopback
        "fd00::1",  # ipv6 unique-local
        "::ffff:10.0.0.5",  # ipv4-mapped private
    ],
)
def test_fetch_refuses_blocked_addresses(blocked_ip: str) -> None:
    client = httpx.Client(transport=httpx.MockTransport(_ok_html))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"target.example": blocked_ip})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://target.example/page")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_fetch_pins_to_vetted_ip_and_sends_hostname_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host_header"] = request.headers.get("host", "")
        seen["connect_host"] = request.url.host
        return _ok_html(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        page = fetcher.fetch("http://public.example/article")
    finally:
        client.close()

    assert seen["connect_host"] == "93.184.216.34"  # pinned to the vetted IP
    assert seen["host_header"] == "public.example"  # original hostname preserved
    assert "# Title" in page.markdown
    assert "Evidence." in page.markdown


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_redirect_to_private_address_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example/"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client,
        resolver=_resolver_for(
            {"public.example": "93.184.216.34", "internal.example": "10.0.0.5"}
        ),
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://public.example/start")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_redirect_depth_is_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Always redirect onward to a fresh public path.
        nxt = f"http://public.example/{request.url.path.count('/')}-{id(request)}"
        return httpx.Response(302, headers={"location": nxt})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://public.example/start")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_redirect_loop_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://public.example/loop"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://public.example/loop")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_declared_content_length_over_cap_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(extract, "_MAX_CONTENT_BYTES", 100)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * 500
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://public.example/big")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_streamed_body_over_cap_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(extract, "_MAX_CONTENT_BYTES", 100)

    def handler(request: httpx.Request) -> httpx.Response:
        def stream():
            yield b"x" * 500

        # A streaming body carries no content-length header.
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=stream()
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://public.example/stream")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_non_html_content_type_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/json"}, text="{}"
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://public.example/data")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_non_http_scheme_is_refused() -> None:
    fetcher = WebContentFetcher(resolver=_resolver_for({}))
    with pytest.raises(ContentUnavailableError):
        fetcher.fetch("ftp://public.example/resource")


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_non_success_status_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "text/html"}, text="no")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("http://public.example/missing")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_network_failure_is_normalized_to_typed_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("TLS verification failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WebContentFetcher(
        client=client, resolver=_resolver_for({"public.example": "93.184.216.34"})
    )
    try:
        with pytest.raises(ContentUnavailableError):
            fetcher.fetch("https://public.example/tls-error")
    finally:
        client.close()


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_html_to_markdown_strips_script_and_preserves_evidence() -> None:
    html = """
    <html><body>
      <nav>Home | About</nav>
      <script>steal()</script>
      <style>.x{color:red}</style>
      <h1>Battery Research</h1>
      <p>See <a href="https://example.com/cite">the source</a>.</p>
      <table><tr><td>Cell A</td><td>Cell B</td></tr></table>
      <footer>copyright</footer>
    </body></html>
    """
    markdown = html_to_markdown(html)

    assert "steal()" not in markdown
    assert "color:red" not in markdown
    assert "Home | About" not in markdown
    assert "copyright" not in markdown
    assert "# Battery Research" in markdown
    assert "https://example.com/cite" in markdown
    assert "Cell A" in markdown and "Cell B" in markdown


# @spec[RANCHO_CONTENT_EXTRACTION.md#requirements]
def test_markdown_output_is_size_bounded(monkeypatch) -> None:
    monkeypatch.setattr(extract, "_MAX_MARKDOWN_CHARS", 50)
    html = "<html><body><p>" + "word " * 200 + "</p></body></html>"
    assert len(html_to_markdown(html)) <= 50
