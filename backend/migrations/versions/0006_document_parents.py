"""retrieval: page/section parents + per-user quota limits

Revision ID: 0006_document_parents
Revises: 0005_chunk_pages
Create Date: 2026-09-14 00:00:00.000000

Adds parent-document retrieval ("small-to-big"):

* ``document_parents`` — the larger unit returned to the model for context.
  For paginated formats (PDF) a parent is a source page (a very large page may
  become several parents sharing the page number); for everything else a parent
  is a fixed-size window of the document. Parents are not embedded.
* ``chunks.parent_id`` — links each embedded child chunk to its parent. Only
  children are embedded and searched; the parent's text is what gets returned.

Also tunes the per-user demo quotas: 10 knowledge bases, 25 files each, 10 MB
per file, 100 MB storage. Existing ``user_quotas`` rows still on the previous
defaults are moved to the new limits (custom rows are left untouched).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_document_parents"
down_revision: str | Sequence[str] | None = "0005_chunk_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS_CREATED = sa.Column(
    "created_at",
    sa.DateTime(timezone=True),
    server_default=sa.text("now()"),
    nullable=False,
)
_TS_UPDATED = sa.Column(
    "updated_at",
    sa.DateTime(timezone=True),
    server_default=sa.text("now()"),
    nullable=False,
)


def upgrade() -> None:
    op.create_table(
        "document_parents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "token_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        _TS_CREATED,
        _TS_UPDATED,
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "ordinal", name="uq_document_parents_document_ordinal"
        ),
    )
    op.create_index(
        "ix_document_parents_document_id", "document_parents", ["document_id"]
    )
    op.create_index(
        "ix_document_parents_knowledge_base_id",
        "document_parents",
        ["knowledge_base_id"],
    )

    op.add_column("chunks", sa.Column("parent_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_chunks_parent_id_document_parents",
        "chunks",
        "document_parents",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chunks_parent_id", "chunks", ["parent_id"])

    # Per-user demo quotas (mirrors shared/models/user_quota.py). Rows created
    # before this revision may still hold the old defaults, so move them across.
    op.execute("ALTER TABLE user_quotas ALTER COLUMN max_knowledge_bases SET DEFAULT 10")
    op.execute("ALTER TABLE user_quotas ALTER COLUMN max_files_per_kb SET DEFAULT 25")
    op.execute("ALTER TABLE user_quotas ALTER COLUMN max_files_per_user SET DEFAULT 250")
    op.execute(
        "ALTER TABLE user_quotas ALTER COLUMN max_file_bytes SET DEFAULT 10485760"
    )
    op.execute(
        "ALTER TABLE user_quotas ALTER COLUMN max_storage_bytes SET DEFAULT 104857600"
    )
    op.execute(
        "UPDATE user_quotas SET max_knowledge_bases = 10 "
        "WHERE max_knowledge_bases = 20"
    )
    op.execute(
        "UPDATE user_quotas SET max_files_per_kb = 25 WHERE max_files_per_kb = 20"
    )
    op.execute(
        "UPDATE user_quotas SET max_files_per_user = 250 "
        "WHERE max_files_per_user = 400"
    )
    op.execute(
        "UPDATE user_quotas SET max_file_bytes = 10485760 "
        "WHERE max_file_bytes = 20971520"
    )
    op.execute(
        "UPDATE user_quotas SET max_storage_bytes = 104857600 "
        "WHERE max_storage_bytes = 209715200"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_quotas ALTER COLUMN max_knowledge_bases SET DEFAULT 20")
    op.execute("ALTER TABLE user_quotas ALTER COLUMN max_files_per_kb SET DEFAULT 20")
    op.execute("ALTER TABLE user_quotas ALTER COLUMN max_files_per_user SET DEFAULT 400")
    op.execute(
        "ALTER TABLE user_quotas ALTER COLUMN max_file_bytes SET DEFAULT 20971520"
    )
    op.execute(
        "ALTER TABLE user_quotas ALTER COLUMN max_storage_bytes SET DEFAULT 209715200"
    )
    op.execute(
        "UPDATE user_quotas SET max_knowledge_bases = 20 "
        "WHERE max_knowledge_bases = 10"
    )
    op.execute(
        "UPDATE user_quotas SET max_files_per_kb = 20 WHERE max_files_per_kb = 25"
    )
    op.execute(
        "UPDATE user_quotas SET max_files_per_user = 400 "
        "WHERE max_files_per_user = 250"
    )
    op.execute(
        "UPDATE user_quotas SET max_file_bytes = 20971520 "
        "WHERE max_file_bytes = 10485760"
    )
    op.execute(
        "UPDATE user_quotas SET max_storage_bytes = 209715200 "
        "WHERE max_storage_bytes = 104857600"
    )

    op.drop_index("ix_chunks_parent_id", table_name="chunks")
    op.drop_constraint(
        "fk_chunks_parent_id_document_parents", "chunks", type_="foreignkey"
    )
    op.drop_column("chunks", "parent_id")

    op.drop_index(
        "ix_document_parents_knowledge_base_id", table_name="document_parents"
    )
    op.drop_index("ix_document_parents_document_id", table_name="document_parents")
    op.drop_table("document_parents")
