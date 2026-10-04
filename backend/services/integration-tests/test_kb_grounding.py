"""End-to-end knowledge-base grounding: resolution -> planner -> forced step.

Proves the chain that decides whether the agent consults the KB:
a KB must be `ready` to resolve, the planner is told to search it first, and the
runtime force-prepends a KB step even when the planner omits one.
"""

from __future__ import annotations

import sys

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "backend" / "agents"))


def _create_kb(kb_id: str, name: str, status: str) -> None:
    from data.repositories import knowledge_bases as kb_repo

    kb_repo.create_kb(
        "u_test",
        kb_id=kb_id,
        name=name,
        description="d",
        status=status,
        embed_model="amazon.titan-embed-text-v2:0",
        image_embed_model="amazon.titan-embed-image-v1",
        embedding_dim=1024,
        chunk_size=512,
        chunk_overlap=64,
    )


def test_knowledge_base_grounding_end_to_end(fake_storage):
    from agentflow import planner
    from agentflow.store import resolve_knowledge_bases

    _create_kb("kb-resume", "my-resume", "ready")
    _create_kb("kb-processing", "still-ingesting", "processing")

    # Only ready KBs resolve; a still-ingesting KB is dropped.
    resolved = resolve_knowledge_bases("u_test", ["kb-resume", "kb-processing"])
    assert resolved == [{"id": "kb-resume", "name": "my-resume"}]
    names = [kb["name"] for kb in resolved]

    # The planner input names the KBs and mandates searching them first.
    prompt = planner._planner_prompt(
        "Can I get 60 LPA in Japan with my profile?",
        "p",
        ["search-user-knowledge-bases", "web-search"],
        names,
        [],
    )
    assert "MUST search these first" in prompt
    assert "my-resume" in prompt

    # Even when the planner omits the KB step, the runtime force-prepends one.
    plan = planner._clean_plan(
        {
            "subQueries": [
                {"query": "q", "todos": [{"title": "web", "tool": "web-search"}]}
            ]
        },
        frozenset(),
        frozenset({"search-user-knowledge-bases", "web-search"}),
    )
    forced = planner.ensure_knowledge_plan(plan, names)
    assert forced["subQueries"][0]["todos"][0]["tool"] == "search-user-knowledge-bases"

    # The folded execution input runs the KB search before the web search.
    text = planner.execution_input("Can I get 60 LPA?", forced)
    assert "search-user-knowledge-bases" in text
    assert text.index("search-user-knowledge-bases") < text.index("web-search")
