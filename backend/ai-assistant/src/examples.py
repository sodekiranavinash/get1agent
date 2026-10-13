"""The example questions AI Assistant offers — used for the off-topic nudge and starters.

One source of truth for both: when AI Assistant declines a non-platform question it ships
three or four of these as **tappable chips** (one tap re-asks it), and the dialog
opens with route-aware starters. `frontend/src/content/aiAssistantStarters.ts` is generated
from this file, so the two can never drift.

The bar for a question here is that it must be one a real user would actually type,
and that the corpus can actually answer:

* **specific, not promotional** — "How do I put my own documents behind an agent?"
  rather than "What can I do on this platform?", which is a question the assistant
  can only answer with a feature list nobody asked for;
* **task-shaped** — it names the thing the user is trying to do, so one tap puts
  them on the shortest path to doing it;
* **grounded in the generated documents** — every starter maps onto pages AI Assistant
  actually has, so a starter is never a dead end that ends in "I don't have that
  documented".
"""

from __future__ import annotations

#: Route-specific questions, most specific first. The key is matched by path
#: prefix, so `/agent-builder` also covers `/agent-builder/anything`.
BY_ROUTE: dict[str, tuple[str, ...]] = {
    "/knowledge-bases": (
        "How do I put my own documents behind an agent?",
        "Why is my document still processing?",
        "When should I use a knowledge base instead of Storage?",
    ),
    "/storage": (
        "What is Storage for, and when should I use it?",
        "How do I attach a file to a single run?",
        "How is Storage different from a knowledge base?",
    ),
    "/agent-builder": (
        "How do I give my agent access to my documents?",
        "Which model should I pick for my agent?",
        "What does the answer mode setting change?",
    ),
    "/workflow-builder": (
        "When should I use swarm instead of graph?",
        "How do I run two agents in parallel?",
        "How does an agent in a workflow inherit its own settings?",
    ),
    "/mcp-builder": (
        "How do I build a custom tool from a description?",
        "What can a custom tool reach that the code interpreter cannot?",
        "How do I test a tool before an agent uses it?",
    ),
    "/agent-skills": (
        "What is a skill, and when does my agent load one?",
        "How do I import a skill from a repository?",
        "How do skills differ from tools?",
    ),
    "/tools": (
        "Which tools does an agent get by default?",
        "How do I connect a remote MCP server?",
        "How do I stop an agent from using the network?",
    ),
    "/chat": (
        "How do I make an agent check with me before it acts?",
        "Where do the citations in an answer come from?",
        "Why did the composer stop accepting messages?",
    ),
    "/evaluations": (
        "How do I find out whether my agent is actually good?",
        "What is a judge model?",
        "How do I build an evaluation dataset from real runs?",
    ),
    "/traces": (
        "How do I find out why a run failed?",
        "How do I see how many tokens a run used?",
        "How long does a trace stay available?",
    ),
    "/metrics": (
        "How do I tell whether my agents are getting more expensive?",
        "Which models are the slowest on this account?",
    ),
    "/vault": (
        "How do I run agents on my own API key?",
        "Is anything in the Vault ever sent to a model?",
    ),
    "/guardrails": (
        "How do I block a topic in every answer?",
        "What is the difference between a guardrail and AgentCore Policy?",
    ),
    "/memory": (
        "What do my agents remember about me?",
        "How do I make an agent forget something?",
    ),
    "/usage": (
        "What are the limits on how much I can create?",
        "What happens when my credits run out?",
        "How do I see what I have used this month?",
    ),
    "/scheduled-jobs": (
        "How do I run an agent on a schedule?",
        "Why did my scheduled run not start?",
    ),
    "/agent-store": (
        "How do I share one of my agents with someone else?",
        "What happens if I install an agent someone published?",
    ),
    "/settings": (
        "Where do I set the default model for new agents?",
        "How do I change my timezone for schedules?",
    ),
    "/docs": (
        "How do knowledge, tools and skills fit together?",
        "How do I build my first agent end to end?",
        "How is my data kept private?",
    ),
}

#: The general pool — the first thing a user sees, and the fallback nudge. Each one
#: is a real question a user would type, grounded in a document the corpus actually
#: has, so a tap lands on an answer rather than a feature tour. The widget shows a
#: random handful of these, so opening AI Assistant twice does not look like a static list.
GENERAL: tuple[str, ...] = (
    "How do I put my own documents behind an agent?",
    "What's the difference between a skill and a custom tool?",
    "How do I see what a run actually cost?",
    "How do I run an agent every morning?",
    "Why is my document still processing?",
    "Which model should I pick for my agent?",
    "How do I make an agent check with me before it acts?",
    "How do I run agents on my own API key?",
    "What happens when my credits run out?",
    "How do I find out why a run failed?",
    "What are the limits on how much I can create?",
    "How do I share one of my agents with someone else?",
    "When should I use a knowledge base instead of Storage?",
    "How do I stop an agent from using the network?",
    "How do I test a custom tool before an agent uses it?",
    "Why did my search return nothing?",
    "What do my agents remember about me?",
    "How do I block a topic in every answer?",
    "How do I run two agents in parallel?",
    "How do I import a skill from a repository?",
    "How do I see how many tokens a run used?",
    "What is the difference between a guardrail and AgentCore Policy?",
    "Where do the citations in an answer come from?",
    "How long does a trace stay available?",
    "Why did my scheduled run not start?",
)

#: How many questions the off-topic nudge ships (its tappable chips).
MAX_EXAMPLES = 4

#: How many questions the dialog opens with, and how many of those are specific to
#: the page the user is on. The rest are drawn at random from :data:`GENERAL`, which
#: is what makes the opening set change between visits.
STARTER_COUNT = 4
STARTER_ROUTE_COUNT = 2


def _matches(route: str) -> tuple[str, ...]:
    if not route:
        return ()
    path = route.split("?", 1)[0].split("#", 1)[0]
    best: tuple[str, ...] = ()
    best_length = 0
    for prefix, questions in BY_ROUTE.items():
        if path == prefix or path.startswith(prefix + "/"):
            if len(prefix) > best_length:
                best, best_length = questions, len(prefix)
    return best


def examples_for(route: str = "", limit: int = MAX_EXAMPLES) -> list[str]:
    """Up to ``limit`` example questions for wherever the user opened AI Assistant."""
    specific = list(_matches(route))
    combined = specific + [q for q in GENERAL if q not in specific]
    return combined[: max(1, limit)]


def starters_for(route: str = "", limit: int = 3) -> list[str]:
    """The questions the dialog opens with (usually fewer than a nudge)."""
    return examples_for(route, limit=limit)
