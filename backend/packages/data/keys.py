"""Key builders for the single-table design.

Layout (see docs/design/design-b-dynamodb-s3.md Part 6):

    Identity      SUB#<sub>        #IDENTITY     (sub -> internal userId)
    User          USER#<userId>    #PROFILE      (userId is a short base32 id)
    Settings      USER#<userId>    #SETTINGS
    Notifications USER#<userId>    #NOTIF
    Quota         USER#<userId>    #QUOTA
    Consent       USER#<userId>    #CONSENT     (DPDP consent record)
    KnowledgeBase USER#<userId>    KB#<name>
    Document      KB#<kbId>        DOC#<lowerFileName>
    Tag           DOC#<docId>      TAG#<lowerName>
    Event         DOC#<docId>      EVENT#<createdAt>#<seq>
    Skill         USER#<userId>    SKILL#<lowerName>
    Custom server USER#<userId>    CSERVER#<slug>
    Custom tool   USER#<userId>    CTOOL#<slug>#<toolName>
    Agent         USER#<userId>    AGENT#<lowerName>
    Workflow      USER#<userId>    WORKFLOW#<lowerName>
    Storage file  USER#<userId>    STORAGE#<fileId>
    Vault secret  USER#<userId>    VAULT#<name>        (encrypted; name is the reference slug)
    Session       USER#<userId>    CONV#<conversationId>
    Conversation  USER#<userId>    CHAT#<globalId>       (chat/builder conversations)
    Playground    USER#<userId>    PGSESSION#<sessionId> (custom-tool build chats)
    Schedule      USER#<userId>    SCHEDULE#<kind>#<targetId> (cron registry)
    MCP conn      USER#<userId>    MCPCONN#<connId>
    MCP OAuth state USER#<userId>  MCPSTATE#<state>   (TTL, single-use)
    Eval run      USER#<userId>    EVALRUN#<runId>
    Eval result   EVALRUN#<runId>  CASE#<caseId>      (per-case metrics)
    Support ticket USER#<userId>   SUPPORT#<ticketId> (metadata; GSI3 SUPPORT#all)
    Support message SUPPORT#<ticketId> MSG#<createdAt>#<seq>
    Security report USER#<userId>  SREPORT#<reportId> (one-way; GSI3 SREPORT#all)
    Notification  USER#<userId>    NOTIF#<id>        (feed item; TTL 90 days)

Conversations are numbered by a single global atomic counter
(``COUNTER#conversations`` / ``#SEQ``); the item carries a byUser GSI2 key
(recency sidebar) and a byId GSI1 key namespaced per agent
(``CHATAGENT#<agentId>``) so the builder can list an agent's runs.

Published agents are additionally projected onto GSI3 under the shared
``AGENTLIB#public`` partition (``<publishedAt>#<agentId>``) so the public
library can be listed globally without a Scan.

The internal ``userId`` is a short base32 id minted on first login; the Auth0
``sub`` is stored as an attribute and resolved through the ``SUB#<sub>``
identity item.

GSI1 "byId"        resolves a KB/document/skill/vault secret by its UUID.
GSI2 "byUser/type" lists a user's KBs/skills/tags/documents by prefix.
GSI3 "byStatus/time" serves the watchdog and the recent-events feed.
"""

from __future__ import annotations

# GSI attribute names.
GSI1 = ("gsi1pk", "gsi1sk")
GSI2 = ("gsi2pk", "gsi2sk")
GSI3 = ("gsi3pk", "gsi3sk")

META = "#META"

PROFILE_SK = "#PROFILE"
IDENTITY_SK = "#IDENTITY"
SETTINGS_SK = "#SETTINGS"
NOTIF_SK = "#NOTIF"
QUOTA_SK = "#QUOTA"
# DPDP consent record (separate from the profile so the login upsert cannot
# clobber it).
CONSENT_SK = "#CONSENT"

KB_PREFIX = "KB#"
DOC_PREFIX = "DOC#"
TAG_PREFIX = "TAG#"
EVENT_PREFIX = "EVENT#"
SKILL_PREFIX = "SKILL#"
CSERVER_PREFIX = "CSERVER#"
CTOOL_PREFIX = "CTOOL#"
AGENT_PREFIX = "AGENT#"
WORKFLOW_PREFIX = "WORKFLOW#"
STORAGE_PREFIX = "STORAGE#"
VAULT_PREFIX = "VAULT#"
CONV_PREFIX = "CONV#"
CHAT_PREFIX = "CHAT#"
PG_SESSION_PREFIX = "PGSESSION#"
FEEDBACK_PREFIX = "FEEDBACK#"
MCPCONN_PREFIX = "MCPCONN#"
MCPSTATE_PREFIX = "MCPSTATE#"
EVAL_RUN_PREFIX = "EVALRUN#"
TRACE_PREFIX = "TRACE#"
SCHEDULE_PREFIX = "SCHEDULE#"
# User support threads (user <-> admin) and one-way security reports.
SUPPORT_PREFIX = "SUPPORT#"
SUPPORT_MESSAGE_PREFIX = "MSG#"
SECURITY_REPORT_PREFIX = "SREPORT#"
# User notifications feed (one small item per notification under USER#<userId>).
# Distinct from the `#NOTIF` notification-*preferences* item.
NOTIFICATION_PREFIX = "NOTIF#"
# Sort-key prefix for per-case run results under an ``EVALRUN#<runId>`` partition.
# (Curated datasets/cases live in the LAB# DynamoDB partition.)
EVAL_CASE_PREFIX = "CASE#"
USER_PREFIX = "USER#"
SUB_PREFIX = "SUB#"

# Global conversation counter (single item, atomic ADD). The value is the last
# minted conversation id; the URL uses it directly (/chat/conversation/<id>).
CONV_COUNTER_PK = "COUNTER#conversations"
CONV_COUNTER_SK = "#SEQ"

# Overloaded GSI1 partition for "an agent's conversations" (builder history).
CHAT_AGENT_PK_PREFIX = "CHATAGENT#"

# Overloaded GSI1 partition for "an agent's traces" (trace explorer filter).
TRACE_AGENT_PK_PREFIX = "TRACEAGENT#"
# Zero-pad the numeric id so the base-table sort key stays lexically ordered.
_CONV_ID_WIDTH = 12

# Shared GSI3 partition for the public agent library (sparse: only published
# agents carry it). Sort key is ``<publishedAt>#<agentId>``.
AGENT_PUBLIC_PK = "AGENTLIB#public"

# Shared GSI3 partition for the scheduler (sparse: only enabled schedules carry
# it). Sort key is ``<nextRunAt>#<userId>`` so the scheduler can query every due
# schedule across all users in one range query.
SCHEDULE_DUE_PK = "SCHEDULES#enabled"

# Shared GSI3 partitions for the admin console. Both are sparse (only support
# tickets / security reports carry them) so an admin lists everything with one
# Query instead of a Scan.
SUPPORT_ALL_PK = "SUPPORT#all"
SECURITY_ALL_PK = "SREPORT#all"


def user_pk(user_id: str) -> str:
    return f"{USER_PREFIX}{user_id}"


def sub_pk(sub: str) -> str:
    """Partition of the identity item that maps an Auth0 ``sub`` to a userId."""
    return f"{SUB_PREFIX}{sub}"


def kb_sk(name: str) -> str:
    return f"{KB_PREFIX}{name.lower()}"


def doc_pk(kb_id: str) -> str:
    return f"KB#{kb_id}"


def doc_sk(file_name: str) -> str:
    return f"{DOC_PREFIX}{file_name.lower()}"


def doc_ref_pk(doc_id: str) -> str:
    """Tags and events hang off the document id, not the document's KB key."""
    return f"{DOC_PREFIX}{doc_id}"


def tag_sk(name: str) -> str:
    return f"{TAG_PREFIX}{name.lower()}"


def event_sk(created_at: str, seq: str) -> str:
    return f"{EVENT_PREFIX}{created_at}#{seq}"


def skill_sk(name: str) -> str:
    return f"{SKILL_PREFIX}{name.lower()}"


def custom_server_sk(slug: str) -> str:
    """A user-defined MCP server (a group of Python tools)."""
    return f"{CSERVER_PREFIX}{slug.lower()}"


def custom_tool_sk(server_slug: str, tool_name: str) -> str:
    """One Python tool inside a user-defined MCP server."""
    return f"{CTOOL_PREFIX}{server_slug.lower()}#{tool_name}"


def agent_sk(name: str) -> str:
    return f"{AGENT_PREFIX}{name.lower()}"


def agent_public_sk(published_at: str, agent_id: str) -> str:
    """GSI3 sort key for a published agent in the shared public library."""
    return f"{published_at}#{agent_id}"


def workflow_sk(name: str) -> str:
    return f"{WORKFLOW_PREFIX}{name.lower()}"


def storage_sk(file_id: str) -> str:
    """A user's uploaded file in the standalone storage area (not a KB)."""
    return f"{STORAGE_PREFIX}{file_id}"


def vault_sk(name: str) -> str:
    """A user's encrypted secret; ``name`` is the ``{{vault:name}}`` slug."""
    return f"{VAULT_PREFIX}{name.lower()}"


def conv_sk(conversation_id: str) -> str:
    return f"{CONV_PREFIX}{conversation_id}"


def chat_sk(conversation_id: int | str) -> str:
    """Base-table sort key for a chat/builder conversation (global numeric id)."""
    return f"{CHAT_PREFIX}{int(conversation_id):0{_CONV_ID_WIDTH}d}"


def chat_by_user_sk(updated_at: str, conversation_id: int | str) -> str:
    """GSI2 ``byUser`` sort key: the sidebar lists conversations by recency."""
    return f"{CHAT_PREFIX}{updated_at}#{int(conversation_id)}"


def chat_agent_pk(agent_id: str) -> str:
    """Overloaded GSI1 partition listing one agent's conversations."""
    return f"{CHAT_AGENT_PK_PREFIX}{agent_id}"


def chat_agent_sk(updated_at: str, conversation_id: int | str) -> str:
    """GSI1 sort key for the per-agent conversation list."""
    return f"{updated_at}#{int(conversation_id)}"


def feedback_sk(run_id: str) -> str:
    """One run's user feedback (thumbs + comment), keyed by the run id."""
    return f"{FEEDBACK_PREFIX}{run_id}"


def playground_session_sk(session_id: str) -> str:
    """Base-table sort key for one Playground build-chat session."""
    return f"{PG_SESSION_PREFIX}{session_id}"


def playground_by_user_sk(updated_at: str, session_id: str) -> str:
    """GSI2 ``byUser`` sort key: the Playground history lists sessions by recency."""
    return f"{PG_SESSION_PREFIX}{updated_at}#{session_id}"


def mcp_conn_sk(conn_id: str) -> str:
    """A user's connection to one remote MCP server (metadata + tokens)."""
    return f"{MCPCONN_PREFIX}{conn_id}"


def mcp_state_sk(state: str) -> str:
    """Single-use, short-lived OAuth ``state`` for an in-flight connection."""
    return f"{MCPSTATE_PREFIX}{state}"


# --- evaluation runs ---------------------------------------------------------


def eval_run_sk(run_id: str) -> str:
    """Base-table sort key for one evaluation run (owned by the user)."""
    return f"{EVAL_RUN_PREFIX}{run_id}"


def eval_run_by_user_sk(updated_at: str, run_id: str) -> str:
    """GSI2 ``byUser`` sort key: the runs list is ordered by recency."""
    return f"{EVAL_RUN_PREFIX}{updated_at}#{run_id}"


def eval_results_pk(run_id: str) -> str:
    """Partition holding one run's per-case results."""
    return f"{EVAL_RUN_PREFIX}{run_id}"


def eval_case_sk(case_id: str) -> str:
    """Sort key for a per-case eval result under an ``EVALRUN#`` partition."""
    return f"{EVAL_CASE_PREFIX}{case_id}"


# --- agent-run traces ---------------------------------------------------------


def trace_sk(trace_id: str) -> str:
    """Base-table sort key for one run's trace index item (owned by the user)."""
    return f"{TRACE_PREFIX}{trace_id}"


def trace_by_user_sk(started_at: str, trace_id: str) -> str:
    """GSI2 ``byUser`` sort key: the traces list is ordered by recency."""
    return f"{TRACE_PREFIX}{started_at}#{trace_id}"


def trace_by_agent_sk(started_at: str, trace_id: str) -> str:
    """GSI1 ``byId`` sort key: an agent's traces (``<startedAt>#<traceId>``)."""
    return f"{started_at}#{trace_id}"


def trace_agent_pk(agent_id: str) -> str:
    """Overloaded GSI1 partition listing one agent's traces."""
    return f"{TRACE_AGENT_PK_PREFIX}{agent_id}"


def schedule_sk(kind: str, target_id: str) -> str:
    """One schedule registry row: the cron for an agent or workflow."""
    return f"{SCHEDULE_PREFIX}{kind}#{target_id}"


def schedule_due_sk(next_run_at: str, user_id: str) -> str:
    """GSI3 ``byStatus`` sort key: ``<nextRunAt>#<userId>`` (lexically ordered)."""
    return f"{next_run_at}#{user_id}"


# --- support & security -------------------------------------------------------


def support_ticket_sk(ticket_id: str) -> str:
    """A user's support ticket metadata (under the user's partition)."""
    return f"{SUPPORT_PREFIX}{ticket_id}"


def support_partition_pk(ticket_id: str) -> str:
    """Partition holding one support thread's messages."""
    return f"{SUPPORT_PREFIX}{ticket_id}"


def support_message_sk(created_at: str, seq: str) -> str:
    """A single message in a support thread, ordered by creation time."""
    return f"{SUPPORT_MESSAGE_PREFIX}{created_at}#{seq}"


def support_all_sk(updated_at: str, ticket_id: str) -> str:
    """GSI3 ``byStatus`` sort key: ``<updatedAt>#<ticketId>`` (newest first)."""
    return f"{updated_at}#{ticket_id}"


def notification_sk(notification_id: str) -> str:
    """One user notification under the user's partition (the feed item)."""
    return f"{NOTIFICATION_PREFIX}{notification_id}"


def security_report_sk(report_id: str) -> str:
    """A user's one-way security report (under the user's partition)."""
    return f"{SECURITY_REPORT_PREFIX}{report_id}"


def security_all_sk(created_at: str, report_id: str) -> str:
    """GSI3 ``byStatus`` sort key: ``<createdAt>#<reportId>`` (newest first)."""
    return f"{created_at}#{report_id}"
