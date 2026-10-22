# Prompt library

Every prompt the platform sends to a model lives here, one `.md` file each,
grouped by the area that owns it.

```
prompts/
  agent/          single-agent runtime: system-prompt blocks, planner, router, HITL
  workflow/       multi-agent host / member orchestration
  ai-assistant/   the in-product assistant: rules, scaffolds, classifier
  evals/          LLM-judge rubrics
  ingestion/      knowledge-graph extraction
  custom-tools/   MCP tool generator
  vault/          provider connectivity probe
```

Prompt wording is product copy: it is read by a model, reviewed by people who do
not write Python, and tuned far more often than the code around it. Keeping it
inline in `.py` files made it hard to find and impossible to review as prose, so
the text lives in `.md` and is loaded at runtime by this package.

```python
from prompts import render as render_prompt
from prompts import text as prompt_text

prompt_text("agent/grounding")                    # the file, verbatim
render_prompt("workflow/team", members="…")       # with {{placeholders}} filled
```

The name is the path — `agent/grounding` is `agent/grounding.md`.

## Rules

- **The file is the prompt.** No frontmatter, no heading, no code fence. The one
  trailing newline an editor adds is dropped on read, so a file and the string
  constant it replaced are byte-identical.
- **`{{placeholder}}` is a slot**, filled with `render_prompt(...)`. Never
  `str.format` — several prompts contain literal JSON and `format` chokes on
  their braces. A missing value raises instead of leaking `{{name}}` to the model.
- **Group by area, name plainly.** `agent/answer-mode.summarize`,
  `workflow/host.swarm`, `evals/faithfulness`. No dotted prefixes.
- **Loading is fail-loud.** A prompt that did not make it into an artifact raises
  `PromptError` naming the missing file and listing what is available — it never
  sends an empty system message.
- **Reads are cached** (`functools.lru_cache`), so the cost is one small file read
  per container, paid before the model call it feeds.

## Why reading from disk is safe here

`backend/packages/prompts` is copied **whole** into every artifact that uses it:
each Lambda Makefile lists it in `PACKAGES` (`cp -R packages/prompts
dist/prompts`) and both containers do `COPY packages ./packages`. A `.md` next to
`__init__.py` therefore travels with the code, and `Path(__file__).parent`
resolves in every context the platform runs in — a Lambda (`/var/task/prompts`),
the AgentCore runtime (`/app/packages/prompts`), the local Floci stack and a
source checkout.

**Adding a prompt to a new artifact means adding `prompts` to that Makefile's
`PACKAGES`.** The Infra workflow asserts the user-api and ai-assistant zips
contain `prompts/agent/grounding.md`, and the integration test loads every file.

## What does not belong here

- **Tool descriptions.** The agent framework builds JSON schemas from the
  function signature and docstring; they are a code contract, not prose.
- **A user's own prompt.** Saved agents, workflows and skills carry their own
  text in DynamoDB — that is user content.
- **Skill bodies** (`SKILL.md`) — authored by users and by the skills registry.
- **One-off strings that assemble runtime values** into a sentence, where the
  value is the point rather than the wording.

## Adding or changing a prompt

1. Add/edit the `.md` file under the right group folder.
2. Reference it by name in the module that builds the prompt (`prompt_text` for a
   fixed block, `render_prompt` for one with slots).
3. `make test` — `test_prompt_library.py` loads every file, checks placeholders
   are fillable, and fails on an orphan that nothing references.
4. Changing a prompt is a deploy: the text is bundled, not fetched.
