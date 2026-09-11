"""create knowledge bases, documents, tags and quotas

Revision ID: 0002_knowledge_bases
Revises: 0001_users
Create Date: 2026-09-11 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_knowledge_bases"
down_revision: str | Sequence[str] | None = "0001_users"
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
        "user_quotas",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "max_file_bytes",
            sa.BigInteger(),
            server_default=sa.text("52428800"),
            nullable=False,
        ),
        sa.Column(
            "max_files_per_kb",
            sa.Integer(),
            server_default=sa.text("10"),
            nullable=False,
        ),
        _TS_CREATED,
        _TS_UPDATED,
        sa.CheckConstraint(
            "max_file_bytes > 0",
            name="ck_user_quotas_max_file_bytes_positive",
        ),
        sa.CheckConstraint(
            "max_files_per_kb > 0",
            name="ck_user_quotas_max_files_per_kb_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_quotas_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_quotas"),
    )

    op.create_table(
        "knowledge_bases",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'ready'"),
            nullable=False,
        ),
        _TS_CREATED,
        _TS_UPDATED,
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'failed')",
            name="ck_knowledge_bases_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_knowledge_bases_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_bases"),
    )
    op.create_index(
        "ix_knowledge_bases_user_id",
        "knowledge_bases",
        ["user_id"],
    )

    op.create_table(
        "documents",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column(
            "size_bytes",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        _TS_CREATED,
        _TS_UPDATED,
        sa.CheckConstraint(
            "source IN ('upload', 'inline')",
            name="ck_documents_source_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'uploaded', 'processing', 'ready', 'failed')",
            name="ck_documents_status_valid",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_documents_size_bytes_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_documents_knowledge_base_id_knowledge_bases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_documents_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("s3_key", name="uq_documents_s3_key"),
    )
    op.create_index(
        "ix_documents_knowledge_base_id",
        "documents",
        ["knowledge_base_id"],
    )

    op.create_table(
        "document_tags",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        _TS_CREATED,
        _TS_UPDATED,
        sa.CheckConstraint(
            "char_length(description) >= 30",
            name="ck_document_tags_description_min_length",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_tags_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_tags"),
        sa.UniqueConstraint(
            "document_id",
            "name",
            name="uq_document_tags_document_id_name",
        ),
    )


def downgrade() -> None:
    op.drop_table("document_tags")
    op.drop_index("ix_documents_knowledge_base_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_knowledge_bases_user_id", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
    op.drop_table("user_quotas")
