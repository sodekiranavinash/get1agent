"""AgentCore Runtime entrypoint for the get1agent agent container.

Runs a saved agent with the Strands Agents framework and streams normalized SSE
events. Implements the AgentCore Runtime HTTP contract through
``BedrockAgentCoreApp`` (``POST /invocations`` streaming, ``GET /ping``).

The single-agent path lives in ``agentflow``; multi-agent workflow orchestration
will be added as a sibling package and dispatched here.

Run locally:

    OPENCODE_API_KEY=... DYNAMODB_ENDPOINT_URL=http://localhost:8000 python main.py
"""

from __future__ import annotations

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agentflow.observability import init_tracing
from agentflow.run import run_agent_stream
from workflow.run import run_workflow_stream

# Must run before BedrockAgentCoreApp() so the AgentCore baggage span processor
# (and every Strands tracer) registers on the Langfuse tracer provider.
init_tracing()

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context=None):
    # A workflow run carries a ``workflowId``; everything else is a single agent.
    is_workflow = isinstance(payload, dict) and str(payload.get("workflowId") or "").strip()
    stream = run_workflow_stream(payload, context) if is_workflow else run_agent_stream(payload, context)
    async for event in stream:
        yield event


if __name__ == "__main__":
    # AgentCore requires port 8080 in the container; AGENT_PORT lets local dev
    # move off it (the Floci reranker also maps host 8080).
    app.run(port=int(os.environ.get("AGENT_PORT", "8080")))
