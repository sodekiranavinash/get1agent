"""ingestion: pgvector chunks, document images, events

Revision ID: 0003_ingestion
Revises: 0002_knowledge_bases
Create Date: 2026-09-12 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.types import Vector

revision: str = "0003_ingestion"
down_revision: str | Sequence[str] | None = "0002_knowledge_bases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024

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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "documents", sa.Column("embed_model", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "documents",
        sa.Column("image_embed_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "image_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("chunk_hash", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "token_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
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
        sa.UniqueConstraint("document_id", "chunk_hash"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_knowledge_base_id", "chunks", ["knowledge_base_id"])
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "document_images",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
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
        sa.UniqueConstraint("document_id", "content_hash"),
    )
    op.create_index(
        "ix_document_images_document_id", "document_images", ["document_id"]
    )
    op.create_index(
        "ix_document_images_knowledge_base_id",
        "document_images",
        ["knowledge_base_id"],
    )
    op.execute(
        "CREATE INDEX ix_document_images_embedding_hnsw ON document_images "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "ingestion_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        _TS_CREATED,
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ingestion_events_knowledge_base_id",
        "ingestion_events",
        ["knowledge_base_id"],
    )
    op.create_index(
        "ix_ingestion_events_document_id", "ingestion_events", ["document_id"]
    )
    op.create_index(
        "ix_ingestion_events_created_at", "ingestion_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_events_created_at", table_name="ingestion_events")
    op.drop_index("ix_ingestion_events_document_id", table_name="ingestion_events")
    op.drop_index(
        "ix_ingestion_events_knowledge_base_id", table_name="ingestion_events"
    )
    op.drop_table("ingestion_events")

    op.execute("DROP INDEX IF EXISTS ix_document_images_embedding_hnsw")
    op.drop_index(
        "ix_document_images_knowledge_base_id", table_name="document_images"
    )
    op.drop_index("ix_document_images_document_id", table_name="document_images")
    op.drop_table("document_images")

    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_index("ix_chunks_knowledge_base_id", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")

    op.drop_column("documents", "image_count")
    op.drop_column("documents", "chunk_count")
    op.drop_column("documents", "image_embed_model")
    op.drop_column("documents", "embed_model")
