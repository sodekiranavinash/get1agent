"""The prompt library is complete, loadable and free of orphans.

Prompts are now bundled Markdown rather than string constants, which introduces one
new failure mode: a prompt that is referenced in code but missing from an artifact
(a package not listed in a Makefile's ``PACKAGES``, a renamed file, a new
deployable that forgot the library). These tests make that a build failure instead
of an empty system prompt at run time, and they keep the library honest — every
file is used, every placeholder is fillable, and every name resolves.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from prompts import PromptError
from prompts import PROMPT_DIR
from prompts import names, render, text

BACKEND = pathlib.Path(__file__).resolve().parents[2]
LIBRARY_DIR = BACKEND / "packages" / "prompts"

# Directories that hold no application source, or would trivially satisfy the
# orphan check by mentioning a name.
_SKIP = {"__pycache__", ".venv", "node_modules", "dist", "tests"}

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _source() -> str:
    blobs: list[str] = []
    for path in BACKEND.rglob("*.py"):
        if any(part in _SKIP for part in path.parts):
            continue
        if LIBRARY_DIR in path.parents:
            continue
        blobs.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(blobs)


def test_every_prompt_file_resolves() -> None:
    found = names()
    assert found, "the prompt library is empty"
    for name in found:
        body = text(name)
        assert body.strip(), f"{name}.md is empty"
        assert not body.endswith("\n"), (
            f"{name}.md keeps a trailing newline — the loader drops exactly one, "
            "so a file must not be written with more"
        )


def test_names_match_the_directory() -> None:
    on_disk = {
        f"{path.parent.name}/{path.stem}" for path in PROMPT_DIR.glob("*/*.md")
    }
    assert set(names()) == on_disk


def test_names_are_grouped_by_area() -> None:
    groups = {name.split("/", 1)[0] for name in names()}
    assert groups == {
        "agent",
        "workflow",
        "ai-assistant",
        "evals",
        "ingestion",
        "custom-tools",
        "vault",
    }


def test_placeholders_are_fillable() -> None:
    """Every ``{{slot}}`` in every prompt can be rendered."""
    for name in names():
        slots = set(_PLACEHOLDER.findall(text(name)))
        rendered = render(name, **{slot: f"<{slot}>" for slot in slots})
        assert re.search(r"\{\{\s*[a-zA-Z0-9_]+\s*\}\}", rendered) is None, name
        for slot in slots:
            assert f"<{slot}>" in rendered, f"{name}: {slot} was not substituted"


def test_render_rejects_a_missing_value() -> None:
    named = [name for name in names() if _PLACEHOLDER.search(text(name))]
    assert named, "expected at least one parameterised prompt"
    with pytest.raises(PromptError):
        render(named[0])


def test_missing_prompt_fails_loudly() -> None:
    with pytest.raises(PromptError) as error:
        text("agent/does-not-exist")
    message = str(error.value)
    # The operator needs to know what to look for, not just that it failed.
    assert "agent/does-not-exist" in message
    assert "agent/grounding" in message  # lists what is available


def test_bad_prompt_name_is_rejected() -> None:
    """A flat or escaping name is a caller bug, not a file lookup."""
    for name in ("grounding", "agent/../core/cache", "/agent/grounding"):
        with pytest.raises(PromptError):
            text(name)


def test_no_orphan_prompts() -> None:
    """Every file is referenced by code, so the library cannot rot."""
    source = _source()
    orphans = []
    for name in names():
        if name in source:
            continue
        # Parameterised families are referenced through an f-string, e.g.
        # f"agent/answer-mode.{mode}" for agent/answer-mode.summarize.
        stem, _, _leaf = name.rpartition(".")
        if stem and f"{stem}.{{" in source:
            continue
        orphans.append(name)
    assert not orphans, f"prompt files nothing references: {orphans}"
