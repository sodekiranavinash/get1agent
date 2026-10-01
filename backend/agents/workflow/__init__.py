"""Multi-agent workflow orchestration (graph + swarm).

A workflow composes saved agents into one run. The runtime builds a Strands
``Graph`` (deterministic, edge-ordered, output passed downstream) or ``Swarm``
(a host agent hands off to its teammates) from the saved workflow config and
streams normalized frames to the client.

The single-agent path lives in ``agentflow``; this package reuses its model,
tool, prompt, session, conversation and observability helpers rather than
duplicating them.
"""
