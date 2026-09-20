"""Key builders for the single-table design.

Layout (see design/design-b-dynamodb-s3.md Part 6):

    Identity      SUB#<sub>        #IDENTITY     (sub -> internal userId)
    User          USER#<userId>    #PROFILE      (userId is a short base32 id)
    Settings      USER#<userId>    #SETTINGS
    Notifications USER#<userId>    #NOTIF
    Quota         USER#<userId>    #QUOTA
    KnowledgeBase USER#<userId>    KB#<name>
    Document      KB#<kbId>        DOC#<lowerFileName>
    Tag           DOC#<docId>      TAG#<lowerName>
    Event         DOC#<docId>      EVENT#<createdAt>#<seq>
    Skill         USER#<userId>    SKILL#<lowerName>
    Agent         USER#<userId>    AGENT#<lowerName>
    Storage file  USER#<userId>    STORAGE#<fileId>
    Session       USER#<userId>    CONV#<conversationId>
    Conversation  USER#<userId>    CHAT#<globalId>       (chat/builder conversations)
    MCP conn      USER#<userId>    MCPCONN#<connId>
    MCP OAuth state USER#<userId>  MCPSTATE#<state>   (TTL, single-use)

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

GSI1 "byId"        resolves a KB/document/skill by its UUID.
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

KB_PREFIX = "KB#"
DOC_PREFIX = "DOC#"
TAG_PREFIX = "TAG#"
EVENT_PREFIX = "EVENT#"
SKILL_PREFIX = "SKILL#"
AGENT_PREFIX = "AGENT#"
STORAGE_PREFIX = "STORAGE#"
CONV_PREFIX = "CONV#"
CHAT_PREFIX = "CHAT#"
MCPCONN_PREFIX = "MCPCONN#"
MCPSTATE_PREFIX = "MCPSTATE#"
USER_PREFIX = "USER#"
SUB_PREFIX = "SUB#"

# Global conversation counter (single item, atomic ADD). The value is the last
# minted conversation id; the URL uses it directly (/chat/conversation/<id>).
CONV_COUNTER_PK = "COUNTER#conversations"
CONV_COUNTER_SK = "#SEQ"

# Overloaded GSI1 partition for "an agent's conversations" (builder history).
CHAT_AGENT_PK_PREFIX = "CHATAGENT#"

# Zero-pad the numeric id so the base-table sort key stays lexically ordered.
_CONV_ID_WIDTH = 12

# Shared GSI3 partition for the public agent library (sparse: only published
# agents carry it). Sort key is ``<publishedAt>#<agentId>``.
AGENT_PUBLIC_PK = "AGENTLIB#public"


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


def agent_sk(name: str) -> str:
    return f"{AGENT_PREFIX}{name.lower()}"


def agent_public_sk(published_at: str, agent_id: str) -> str:
    """GSI3 sort key for a published agent in the shared public library."""
    return f"{published_at}#{agent_id}"


def storage_sk(file_id: str) -> str:
    """A user's uploaded file in the standalone storage area (not a KB)."""
    return f"{STORAGE_PREFIX}{file_id}"


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


def mcp_conn_sk(conn_id: str) -> str:
    """A user's connection to one remote MCP server (metadata + tokens)."""
    return f"{MCPCONN_PREFIX}{conn_id}"


def mcp_state_sk(state: str) -> str:
    """Single-use, short-lived OAuth ``state`` for an in-flight connection."""
    return f"{MCPSTATE_PREFIX}{state}"
