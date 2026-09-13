"""chunks: source page range for citations + retrieval indexes

Revision ID: 0005_chunk_pages
Revises: 0004_kb_ingestion_config
Create Date: 2026-09-13 00:00:00.000000

Adds the read-path groundwork:

* ``chunks.page`` / ``chunks.page_end`` — 1-based source page range for PDFs.
* ``chunks.content_tsv`` — generated full-text vector backing the lexical leg
  of hybrid search, with a GIN index.
* unique ``(user_id, lower(name))`` on ``knowledge_bases`` so a user cannot
  create two knowledge bases with the same name.
* ``document_tags (lower(name))`` index for tag metadata filtering.

This revision has not been applied anywhere yet, so it is extended in place
instead of adding a new head.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_chunk_pages"
down_revision: str | Sequence[str] | None = "0004_kb_ingestion_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("page", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("page_end", sa.Integer(), nullable=True))

    # Lexical leg of hybrid search. `to_tsvector(regconfig, text)` is IMMUTABLE,
    # so it can back a generated STORED column. `simple` keeps matching
    # language-agnostic (the corpus is multi-lingual).
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_chunks_content_tsv ON chunks USING gin (content_tsv)"
    )

    # One knowledge base name per user, case-insensitive.
    op.execute(
        "CREATE UNIQUE INDEX uq_knowledge_bases_user_name "
        "ON knowledge_bases (user_id, lower(name))"
    )

    # Tag metadata filter matches case-insensitively.
    op.execute(
        "CREATE INDEX ix_document_tags_name ON document_tags (lower(name))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_tags_name")
    op.execute("DROP INDEX IF EXISTS uq_knowledge_bases_user_name")
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
    op.drop_column("chunks", "page_end")
    op.drop_column("chunks", "page")
