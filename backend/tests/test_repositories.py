"""DynamoDB repository behaviour (single table + GSIs + counters)."""

from __future__ import annotations

import re

from shared.dynamo.repositories import (
    documents,
    events,
    knowledge_bases as kb,
    quotas,
    settings,
    skills,
    tags,
    users,
)

CLAIMS = {
    "sub": "auth0|repos",
    "https://get1agent.com/email": "repos@example.com",
    "https://get1agent.com/name": "Repos",
}


def _profile():
    return users.upsert_user(CLAIMS)


def _kb(profile, kb_id="11111111-1111-1111-1111-111111111111", name="my-kb"):
    return kb.create_kb(
        profile["userId"],
        kb_id=kb_id,
        name=name,
        description="d",
        status="ready",
        embed_model="m",
        image_embed_model="im",
        embedding_dim=1024,
        chunk_size=512,
        chunk_overlap=64,
    )


def test_user_settings_and_quota():
    profile = _profile()
    sub = profile["userId"]
    assert profile["email"] == "repos@example.com"
    assert profile["fullName"] == "Repos"
    # The Auth0 sub is an attribute; the key is a minted short internal id.
    assert profile["sub"] == "auth0|repos"
    assert sub != "auth0|repos"
    assert re.fullmatch(r"u_[0-9a-hjkmnp-tv-z]{16}", sub)

    # The sub resolves to the same internal id, and the profile is stable.
    assert users.get_user_by_sub("auth0|repos")["userId"] == sub
    assert users.get_user_by_id(sub)["userId"] == sub
    assert users.upsert_user(CLAIMS)["userId"] == sub

    settings.ensure_settings(sub)
    settings.ensure_notification_preferences(sub)
    quotas.ensure_quota(sub)
    settings.update_settings(sub, preferred_theme="light", timezone="Europe/London")
    assert settings.get_settings(sub)["preferredTheme"] == "light"

    quotas.adjust_counters(sub, kb_count=2, file_count=3, storage_bytes=100)
    quota = quotas.get_quota(sub)
    assert (quota.kb_count, quota.file_count, quota.storage_bytes) == (2, 3, 100)
    assert quota.max_knowledge_bases == 10
    quotas.adjust_counters(sub, kb_count=-1)
    assert quotas.get_quota(sub).kb_count == 1


def test_knowledge_base_uniqueness_and_listing():
    profile = _profile()
    sub = profile["userId"]
    _kb(profile)
    quotas.adjust_counters(sub, kb_count=1)

    assert kb.get_kb(sub, "11111111-1111-1111-1111-111111111111")["name"] == "my-kb"
    assert kb.get_kb("someone-else", "11111111-1111-1111-1111-111111111111") is None
    assert [item["name"] for item in kb.list_kbs(sub)] == ["my-kb"]

    try:
        _kb(profile, kb_id="x", name="my-kb")
        raise AssertionError("expected duplicate")
    except kb.DuplicateKnowledgeBase:
        pass

    kb.adjust_doc_count("11111111-1111-1111-1111-111111111111", 1)
    assert kb.get_kb_by_id("11111111-1111-1111-1111-111111111111")["docCount"] == 1


def test_documents_crud_and_status_gsi():
    profile = _profile()
    sub = profile["userId"]
    item = _kb(profile)
    doc = documents.document_item(
        doc_id="22222222-2222-2222-2222-222222222222",
        kb_id=item["kbId"],
        user_id=sub,
        file_name="resume.pdf",
        s3_key="raw/u/k/d/resume.pdf",
        content_type="application/pdf",
        size_bytes=100,
        source="upload",
        status="pending",
    )
    documents.put_document(doc, condition="attribute_not_exists(pk)")
    assert documents.get_document(item["kbId"], "resume.pdf")["docId"] == doc["docId"]
    assert documents.get_document_by_id(doc["docId"])["status"] == "pending"
    assert len(documents.list_documents(item["kbId"])) == 1

    documents.update_document(doc["docId"], status="processing")
    assert documents.find_by_status_older_than("processing", "9999")[0]["docId"] == doc["docId"]

    found = documents.batch_get_documents(
        [{"pk": documents.doc_pk(item["kbId"]), "sk": doc["fileKey"]}]
    )
    assert found[(documents.doc_pk(item["kbId"]), doc["fileKey"])]["docId"] == doc["docId"]

    assert kb.get_kb_by_id(item["kbId"]) is not None
    kb.adjust_processing(item["kbId"], 1)
    assert kb.get_kb_by_id(item["kbId"])["status"] == "processing"
    kb.adjust_processing(item["kbId"], -1)
    assert kb.get_kb_by_id(item["kbId"])["status"] == "ready"


def test_tags_are_grouped_and_denormalized():
    profile = _profile()
    sub = profile["userId"]
    item = _kb(profile)
    doc = documents.document_item(
        doc_id="33333333-3333-3333-3333-333333333333",
        kb_id=item["kbId"],
        user_id=sub,
        file_name="resume.pdf",
        s3_key="raw/u/k/d/resume.pdf",
        content_type="application/pdf",
        size_bytes=10,
        source="upload",
        status="ready",
    )
    documents.put_document(doc)
    tags.replace_tags(sub, doc["docId"], item["kbId"], doc["fileKey"], [("Resume", "cv"), ("Python", "")])

    assert {t["name"] for t in tags.list_tags(sub)} == {"Resume", "Python"}
    assert [t["name"] for t in tags.list_tags_by_kb(sub)[item["kbId"]]] == ["Python", "Resume"]
    assert tags.document_ids_for_tag(sub, "python") == {doc["docId"]}
    assert len(documents.get_document_by_id(doc["docId"])["tags"]) == 2

    tags.delete_tags_for_document(doc["docId"])
    assert tags.list_tags(sub) == []


def test_events_feed():
    profile = _profile()
    sub = profile["userId"]
    item = _kb(profile)
    doc = documents.document_item(
        doc_id="44444444-4444-4444-4444-444444444444",
        kb_id=item["kbId"],
        user_id=sub,
        file_name="resume.pdf",
        s3_key="raw/u/k/d/resume.pdf",
        content_type="application/pdf",
        size_bytes=10,
        source="upload",
        status="uploaded",
    )
    documents.put_document(doc)
    events.emit_event(
        document_id=doc["docId"],
        knowledge_base_id=item["kbId"],
        user_id=sub,
        stage="uploaded",
        status="succeeded",
        message="hi",
        file_name="resume.pdf",
        file_key=doc["fileKey"],
    )
    events.emit_event(
        document_id=doc["docId"],
        knowledge_base_id=item["kbId"],
        user_id=sub,
        stage="extracted",
        status="succeeded",
        message="parsed",
        file_name="resume.pdf",
        file_key=doc["fileKey"],
    )
    listed = events.list_events(sub, limit=10)
    assert len(listed) == 2
    assert listed[0]["stage"] == "extracted"  # newest first
    assert events.list_events(sub, limit=10, kb_id="nope") == []

    # Deleting a document removes its whole timeline.
    assert events.delete_events_for_document(doc["docId"]) == 2
    assert events.list_events(sub, limit=10) == []


def test_skills_crud_and_rename():
    profile = _profile()
    sub = profile["userId"]
    skill = skills.create_skill(
        sub,
        skill_id="55555555-5555-5555-5555-555555555555",
        name="pdf-processing",
        description="d",
        allowed_tools=["web-search"],
        content="body",
        source="write",
    )
    assert skills.count_skills(sub) == 1
    assert skills.get_skill(sub, skill["skillId"])["name"] == "pdf-processing"

    skills.update_skill(
        sub,
        skill["skillId"],
        name="pdf-parsing",
        description="d2",
        allowed_tools=[],
        content="body2",
        source="write",
    )
    assert skills.get_skill(sub, skill["skillId"])["name"] == "pdf-parsing"
    assert skills.get_skill_by_name(sub, "pdf-parsing") is not None
    assert skills.get_skill_by_name(sub, "pdf-processing") is None

    skills.delete_skill(sub, skill["skillId"])
    assert skills.count_skills(sub) == 0
