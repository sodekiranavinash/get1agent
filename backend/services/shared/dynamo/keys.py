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
    Session       USER#<userId>    CONV#<conversationId>

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
CONV_PREFIX = "CONV#"
USER_PREFIX = "USER#"
SUB_PREFIX = "SUB#"


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


def conv_sk(conversation_id: str) -> str:
    return f"{CONV_PREFIX}{conversation_id}"
