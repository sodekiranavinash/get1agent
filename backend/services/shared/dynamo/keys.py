"""Key builders for the single-table design.

Layout (see design/design-b-dynamodb-s3.md Part 6):

    User          USER#<sub>        #PROFILE
    Settings      USER#<sub>        #SETTINGS
    Notifications USER#<sub>        #NOTIF
    Quota         USER#<sub>        #QUOTA
    KnowledgeBase USER#<sub>        KB#<name>
    Document      KB#<kbId>         DOC#<lowerFileName>
    Tag           DOC#<docId>       TAG#<lowerName>
    Event         DOC#<docId>       EVENT#<createdAt>#<seq>
    Skill         USER#<sub>        SKILL#<lowerName>
    Session       USER#<sub>        CONV#<conversationId>

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


def user_pk(sub: str) -> str:
    return f"{USER_PREFIX}{sub}"


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
