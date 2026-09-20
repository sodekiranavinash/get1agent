"""Resolve ``owner/repo`` (like ``npx skills add``) to the skills it contains.

GitHub is the registry: any public repo with ``SKILL.md`` files. We walk the
default branch tree and return each skill's raw URL. Optional ``GITHUB_TOKEN``
raises the unauthenticated rate limit (60/hr).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
TIMEOUT_SECONDS = 10
MAX_SKILLS = 100

_SHORTHAND = re.compile(r"^[\w.-]+/[\w.-]+$")


class RepoError(Exception):
    pass


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "get1agent"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RepoError("Repository not found (is it public?)") from exc
        if exc.code == 403:
            raise RepoError("GitHub rate limit reached; try again later") from exc
        raise RepoError(f"GitHub error ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RepoError(f"Could not reach GitHub: {exc}") from exc


def parse_repo(value: str) -> tuple[str, str, str | None, str | None]:
    """Return ``(owner, repo, ref, subpath)`` from a repo spec."""
    spec = (value or "").strip()
    if not spec:
        raise RepoError("Enter a repository like owner/repo")
    ref: str | None = None
    subpath: str | None = None
    if spec.startswith(("http://", "https://")):
        parsed = urllib.parse.urlsplit(spec)
        if (parsed.hostname or "").lower() not in ("github.com", "www.github.com"):
            raise RepoError("Only github.com repositories are supported")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise RepoError("Enter a repository like owner/repo")
        owner, repo = parts[0], parts[1].removesuffix(".git")
        if len(parts) >= 4 and parts[2] in ("tree", "blob"):
            ref = parts[3]
            subpath = "/".join(parts[4:]) or None
    elif _SHORTHAND.match(spec):
        owner, repo = spec.split("/", 1)
    else:
        raise RepoError("Enter a repository like owner/repo")
    return owner, repo, ref, subpath


def resolve(repo_spec: str) -> dict[str, Any]:
    owner, repo, ref, subpath = parse_repo(repo_spec)
    if not ref:
        info = _get_json(f"{GITHUB_API}/repos/{owner}/{repo}")
        ref = str(info.get("default_branch") or "main")

    tree = _get_json(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(ref)}?recursive=1"
    )
    entries = tree.get("tree") if isinstance(tree, dict) else None
    if not isinstance(entries, list):
        raise RepoError("Could not read the repository tree")

    skills: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = str(entry.get("path") or "")
        if not path.endswith("SKILL.md"):
            continue
        if subpath and not path.startswith(subpath):
            continue
        directory = path[: -len("SKILL.md")].rstrip("/")
        name = directory.rsplit("/", 1)[-1] if directory else repo
        skills.append(
            {
                "name": name,
                "path": path,
                "rawUrl": f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}",
                "sourceUrl": f"https://github.com/{owner}/{repo}/blob/{ref}/{path}",
            }
        )
        if len(skills) >= MAX_SKILLS:
            break

    return {"owner": owner, "repo": repo, "ref": ref, "skills": skills}
