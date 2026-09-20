"""Classify an imported skill as prompt-only or tool-based.

Third-party skills rarely declare ``allowed-tools``; their dependencies live in
the prose. We scan the raw markdown for code-execution and web-search signals to
decide whether the skill needs the built-in servers, and list any sibling files
it references (which we cannot import).
"""

from __future__ import annotations

import re

_CODE_FENCE = re.compile(
    r"```(?:python|py|bash|sh|shell|zsh|javascript|js|node|sql|ruby|go|java|typescript|ts|powershell)\b",
    re.IGNORECASE,
)
_CODE_WORDS = re.compile(
    r"\b(python|bash|shell|subprocess|pip install|npm install|pnpm|execute the|"
    r"run the (?:script|code|command|following)|code interpreter|write a script)\b",
    re.IGNORECASE,
)
_WEB_WORDS = re.compile(
    r"\b(web[ _-]?search|search the web|web search|browse the web|crawl the web|"
    r"web fetch|fetch the (?:url|page|webpage)|google search|internet search)\b",
    re.IGNORECASE,
)

_MD_LINK = re.compile(r"\]\(([^)\s]+)\)")


def classify_skill(markdown: str) -> dict[str, object]:
    """Return ``{kind, suggestedServers}`` for a raw skill document."""
    text = markdown or ""
    needs_code = bool(_CODE_FENCE.search(text) or _CODE_WORDS.search(text))
    needs_web = bool(_WEB_WORDS.search(text))

    suggested: list[str] = []
    if needs_code:
        suggested.append("code-interpreter")
    if needs_web:
        suggested.append("web-search")

    return {
        "kind": "tool" if suggested else "prompt",
        "suggestedServers": suggested,
    }


def referenced_files(markdown: str) -> list[str]:
    """Relative files a skill links to (dropped on import — surfaced as a warning)."""
    files: list[str] = []
    for match in _MD_LINK.finditer(markdown or ""):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if "." not in target:
            continue
        normalised = target.lstrip("./")
        if normalised and normalised not in files:
            files.append(normalised)
    return files
