"""knowledge base ingestion configuration

Revision ID: 0004_kb_ingestion_config
Revises: 0003_ingestion
Create Date: 2026-09-12 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_kb_ingestion_config"
down_revision: str | Sequence[str] | None = "0003_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embed_model",
            sa.String(length=128),
            server_default=sa.text("'amazon.titan-embed-text-v2:0'"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "image_embed_model",
            sa.String(length=128),
            server_default=sa.text("'amazon.titan-embed-image-v1'"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_dim",
            sa.Integer(),
            server_default=sa.text("1024"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "chunk_size",
            sa.Integer(),
            server_default=sa.text("1024"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "chunk_overlap",
            sa.Integer(),
            server_default=sa.text("128"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "chunk_overlap")
    op.drop_column("knowledge_bases", "chunk_size")
    op.drop_column("knowledge_bases", "embedding_dim")
    op.drop_column("knowledge_bases", "image_embed_model")
    op.drop_column("knowledge_bases", "embed_model")
