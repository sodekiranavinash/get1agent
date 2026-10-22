"""The prompt library: every model-facing prompt, grouped by the feature that owns it.

Prompt wording is product copy, not code: it is read by a model, reviewed by
people who do not write Python, and tuned far more often than the code around it.
Keeping it inline in ``.py`` files made it hard to find and impossible to review
as prose, so the text lives here as Markdown and is loaded at runtime.

Layout — one folder per area, one file per prompt::

    prompts/
      agent/          single-agent runtime: system-prompt blocks, planner, router, HITL
      workflow/       multi-agent host / member orchestration
      ai-assistant/   the in-product assistant: rules, scaffolds, classifier
      evals/          LLM-judge rubrics
      ingestion/      knowledge-graph extraction
      custom-tools/   MCP tool generator
      vault/          provider connectivity probe

The name is the path: ``prompt_text("agent/grounding")``.

Conventions
-----------
* The file **is** the prompt: no frontmatter, no heading, no code fence. The
  single trailing newline an editor adds is dropped on read, so a file and the
  string constant it replaced are byte-identical.
* ``{{placeholder}}`` marks a slot. Use :func:`render` to fill it, never
  ``str.format`` — several prompts contain literal JSON and ``format`` would
  choke on their braces.
* Never make a prompt's meaning depend on its file *name*; the name is an
  address, the text is the contract.

Why reading from disk is safe here
----------------------------------
``backend/packages/prompts`` is copied **whole** into every artifact that uses
it: the Lambda Makefiles list it in ``PACKAGES`` (``cp -R packages/prompts
dist/prompts``) and both containers do ``COPY packages ./packages``. A ``.md``
file next to this ``__init__.py`` therefore travels with the code, and
``Path(__file__).parent`` resolves in every context the platform runs in — a
Lambda (``/var/task/prompts``), the AgentCore runtime
(``/app/packages/prompts``), the local Floci stack and a source checkout.
Reads are cached, so the cost is paid once per container and is dwarfed by the
model call that follows.

Anything that is not prose stays in code: tool descriptions (the framework
builds JSON schemas from them), a user's own agent prompt and skill bodies
(user-authored, stored in DynamoDB), and one-off strings that assemble runtime
values are not prompt library material.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = ["PromptError", "PROMPT_DIR", "exists", "names", "render", "text"]

#: Directory holding the prompt folders (``agent/``, ``workflow/``, …).
PROMPT_DIR = Path(__file__).resolve().parent

# "<group>/<name>" — a group folder and a leaf file name, nothing else.
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*$")

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class PromptError(RuntimeError):
    """A prompt file is missing, or a placeholder was not supplied."""


def names() -> tuple[str, ...]:
    """Every prompt name, sorted — for tooling and the library's own tests."""
    return tuple(sorted(f"{path.parent.name}/{path.stem}" for path in PROMPT_DIR.glob("*/*.md")))


def exists(name: str) -> bool:
    return bool(_NAME.match(name)) and (PROMPT_DIR / f"{name}.md").is_file()


@lru_cache(maxsize=None)
def text(name: str) -> str:
    """The prompt ``name`` exactly as it should be sent to the model.

    Raises :class:`PromptError` naming the missing file and listing what is
    available: a prompt that did not make it into an artifact must fail loudly,
    not silently send an empty system message.
    """
    if not _NAME.match(name):
        raise PromptError(
            f"'{name}' is not a prompt name; expected '<group>/<name>', "
            f"e.g. 'agent/grounding'. Known prompts: {', '.join(names()) or '(none)'}"
        )
    path = PROMPT_DIR / f"{name}.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise PromptError(
            f"prompt '{name}' not found at {path}. "
            f"Known prompts: {', '.join(names()) or '(none)'}. If this file is new, "
            f"check that it lives under backend/packages/prompts/ so it is bundled."
        ) from error
    # The newline at the end of the file is an editor artefact, not prompt text.
    return raw[:-1] if raw.endswith("\n") else raw


def render(name: str, /, **values: Any) -> str:
    """Fill the ``{{placeholders}}`` in prompt ``name``.

    A missing value is an error rather than a silent ``{{name}}`` leaking into a
    model prompt.
    """
    template = text(name)

    def _substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise PromptError(
                f"prompt '{name}' needs a value for {{{{{key}}}}}; "
                f"got {sorted(values) or 'nothing'}"
            )
        value = values[key]
        return "" if value is None else str(value)

    return _PLACEHOLDER.sub(_substitute, template)
