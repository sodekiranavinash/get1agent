"""SSRF-guarded HTTP client for the http-fetch MCP tool (standard library only).

This runs in trusted Lambda code (never in the user sandbox), so it is the one
place that may reach the public internet on a user's behalf. Every hop is
validated before any bytes leave the process:

* only ``http``/``https`` URLs, and no credentials embedded in the URL;
* the hostname is resolved and **every** returned address is checked against a
  denylist of loopback / private / link-local / reserved / metadata ranges;
* the TCP connection is pinned to the validated address while the ``Host``
  header and TLS SNI keep the original hostname, so a DNS rebind between the
  check and the connect cannot redirect the request;
* redirects are followed manually and re-validated hop by hop;
* the response size and wall-clock time are capped.

An optional ``allowed_domains`` allowlist can restrict the fetcher to known
hosts (suffix match) on top of the address checks.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 5
DEFAULT_USER_AGENT = "get1agent-http-fetch/1.0"

# Caller-supplied headers that must be dropped: ``host`` would let a caller
# desync the validated host from the request, and the rest are hop-by-hop /
# body-framing headers the HTTP client sets itself (duplicating them corrupts
# the request).
_DROP_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-connection",
        "upgrade",
        "te",
        "trailer",
    }
)

# Ranges not covered by ``ipaddress``'s ``is_private`` that must still be denied.
_EXTRA_BLOCKED_V4 = (ipaddress.ip_network("100.64.0.0/10"),)  # CGNAT
_EXTRA_BLOCKED_V6 = (ipaddress.ip_network("64:ff9b::/96"),)  # NAT64


class FetchError(Exception):
    """The request was rejected by policy or could not be completed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FetchResult:
    status: int
    headers: dict[str, str]
    content_type: str
    body: bytes
    final_url: str
    truncated: bool
    redirects: list[str] = field(default_factory=list)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that dials a pre-validated IP instead of re-resolving."""

    def __init__(self, host: str, ip: str, port: int, timeout: int) -> None:
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self) -> None:  # noqa: D102 - stdlib override
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to an IP, keeping TLS SNI + hostname check."""

    def __init__(
        self, host: str, ip: str, port: int, timeout: int, context: ssl.SSLContext
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._ip = ip

    def connect(self) -> None:  # noqa: D102 - stdlib override
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _blocked(ip_str: str) -> bool:
    """True when ``ip_str`` is a loopback/private/link-local/reserved address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in _EXTRA_BLOCKED_V4)
    return any(ip in net for net in _EXTRA_BLOCKED_V6)


def _resolve(host: str) -> str:
    """Resolve ``host`` and return one validated IP, rejecting blocked ranges."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError("dns_error", f"Could not resolve host: {host}") from exc
    addresses = sorted({info[4][0] for info in infos if info[4]})
    if not addresses:
        raise FetchError("dns_error", f"Could not resolve host: {host}")
    for address in addresses:
        if _blocked(address):
            raise FetchError(
                "blocked_target",
                "Refusing to connect to a private, loopback or reserved address",
            )
    return addresses[0]


def _domain_allowed(host: str, allowed_domains: tuple[str, ...]) -> bool:
    if not allowed_domains:
        return True
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def _validate(url: str, allowed_domains: tuple[str, ...]) -> dict[str, Any]:
    """Parse + policy-check ``url``; return its validated connection parts."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise FetchError("invalid_url", "The URL could not be parsed") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise FetchError("invalid_url", "Only http and https URLs are supported")
    if parts.username or parts.password:
        raise FetchError("invalid_url", "URLs must not embed credentials")

    host = parts.hostname
    if not host:
        raise FetchError("invalid_url", "The URL is missing a host")
    if not _domain_allowed(host, allowed_domains):
        raise FetchError("blocked_target", f"Host not in allowlist: {host}")

    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("invalid_url", "The URL has an invalid port") from exc

    ip = _resolve(host)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "ip": ip,
        "path": path,
    }


def _open_once(
    target: dict[str, Any],
    method: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout: int,
    max_bytes: int,
) -> tuple[int, dict[str, str], bytes]:
    if target["scheme"] == "https":
        context = ssl.create_default_context()
        conn: http.client.HTTPConnection = _PinnedHTTPSConnection(
            target["host"], target["ip"], target["port"], timeout, context
        )
    else:
        conn = _PinnedHTTPConnection(
            target["host"], target["ip"], target["port"], timeout
        )
    try:
        conn.request(method, target["path"], body=body, headers=headers)
        response = conn.getresponse()
        status = response.status
        response_headers = {
            key.lower(): value for key, value in response.getheaders()
        }
        data = response.read(max_bytes + 1)
        return status, response_headers, data
    except (http.client.HTTPException, OSError, ssl.SSLError) as exc:
        raise FetchError("request_failed", f"Request failed: {exc}") from exc
    finally:
        conn.close()


def fetch(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 30,
    max_bytes: int = 10 * 1024 * 1024,
    max_redirects: int = MAX_REDIRECTS,
    allowed_domains: tuple[str, ...] = (),
) -> FetchResult:
    """Fetch ``url``, following (and re-validating) redirects."""
    method = (method or "GET").upper()
    if method not in ALLOWED_METHODS:
        raise FetchError("invalid_request", f"Unsupported method: {method}")

    request_headers = {
        str(key): str(value)
        for key, value in (headers or {}).items()
        if str(key).lower() not in _DROP_HEADERS
    }
    request_headers.setdefault("user-agent", DEFAULT_USER_AGENT)

    current_url = url
    redirects: list[str] = []
    current_method = method
    current_body = body

    for _ in range(max_redirects + 1):
        target = _validate(current_url, allowed_domains)
        status, response_headers, data = _open_once(
            target, current_method, request_headers, current_body, timeout, max_bytes
        )

        location = response_headers.get("location")
        if status in REDIRECT_CODES and location:
            next_url = urllib.parse.urljoin(current_url, location)
            redirects.append(next_url)
            # 303 always becomes GET; 301/302 rewrite non-idempotent methods.
            if status == 303 or (
                status in (301, 302) and current_method not in ("GET", "HEAD")
            ):
                current_method = "GET"
                current_body = None
            current_url = next_url
            continue

        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]
        return FetchResult(
            status=status,
            headers=response_headers,
            content_type=response_headers.get("content-type", ""),
            body=data,
            final_url=current_url,
            truncated=truncated,
            redirects=redirects,
        )

    raise FetchError("too_many_redirects", "The URL redirected too many times")
