"""Shared AI/MCP layer.

Lightweight, dependency-free helpers used by the MCP server, the admin MCP
tester and the user-facing API Lambdas:

* ``ai.auth``       — Auth0 role/claim + active-view checks.
* ``ai.mcp_client`` — a thin MCP JSON-RPC client that talks to the
  ``knowledge-mcp`` Lambda over its direct-invoke transport.
"""

from ai.auth import (
    ADMIN_CLAIM,
    ADMIN_ROLE,
    ROLES_CLAIM,
    VIEW_ADMIN,
    VIEW_HEADER,
    VIEW_USER,
    AuthError,
    active_view,
    is_admin_claims,
    require_admin,
    require_user,
    token_roles,
)
from ai.mcp_client import McpClientError, call_tool, list_tools

__all__ = [
    "ADMIN_CLAIM",
    "ADMIN_ROLE",
    "ROLES_CLAIM",
    "VIEW_ADMIN",
    "VIEW_HEADER",
    "VIEW_USER",
    "AuthError",
    "McpClientError",
    "active_view",
    "call_tool",
    "is_admin_claims",
    "list_tools",
    "require_admin",
    "require_user",
    "token_roles",
]
