"""Safe fetcher for importing skills from public sources.

Skills are fetched from third-party hosts, so this is deliberately narrow:
HTTPS only, an explicit host allowlist, and a size cap. Redirects are followed
by ``urllib`` but the final host is re-checked.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS = {
    "raw.githubusercontent.com",
    "github.com",
    "api.github.com",
    "api.claude-plugins.dev",
    "claude-plugins.dev",
    "claudskills.com",
}

FETCH_TIMEOUT_SECONDS = 10
MAX_SKILL_BYTES = 300_000


class FetchError(Exception):
    pass


def _check(url: str, allowed_hosts: set[str]) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise FetchError("Only https:// URLs can be imported")
    host = (parsed.hostname or "").lower()
    if host not in allowed_hosts:
        raise FetchError(f"Host not allowed: {host or url}")
    return url


def fetch_text(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    timeout: int = FETCH_TIMEOUT_SECONDS,
    max_bytes: int = MAX_SKILL_BYTES,
) -> str:
    """Fetch a small text document from an allowlisted HTTPS host."""
    hosts = allowed_hosts or ALLOWED_HOSTS
    _check(url, hosts)
    request = urllib.request.Request(
        url, headers={"User-Agent": "get1agent", "Accept": "text/plain, */*"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            _check(response.geturl(), hosts)
            data = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"Could not fetch the skill ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"Could not fetch the skill: {exc}") from exc
    if len(data) > max_bytes:
        raise FetchError("Skill file is too large")
    return data.decode("utf-8", "replace")
