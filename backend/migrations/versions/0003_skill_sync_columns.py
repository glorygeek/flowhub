"""Add ClawHub sync columns to skills

Revision ID: 0003_skill_sync_columns
Revises: 0002_run_requests
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_skill_sync_columns"
down_revision: Union[str, None] = "0002_run_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "skills",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.add_column("skills", sa.Column("source_slug", sa.String(length=160), nullable=True))
    op.add_column("skills", sa.Column("source_url", sa.String(length=500), nullable=True))
    op.add_column("skills", sa.Column("owner_handle", sa.String(length=120), nullable=True))
    op.add_column(
        "skills",
        sa.Column("stats", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "skills",
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "skills",
        sa.Column("source_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("skills", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(op.f("ix_skills_source"), "skills", ["source"], unique=False)
    op.create_index(op.f("ix_skills_source_slug"), "skills", ["source_slug"], unique=True)
    op.create_index(op.f("ix_skills_owner_handle"), "skills", ["owner_handle"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_skills_owner_handle"), table_name="skills")
    op.drop_index(op.f("ix_skills_source_slug"), table_name="skills")
    op.drop_index(op.f("ix_skills_source"), table_name="skills")

    op.drop_column("skills", "last_synced_at")
    op.drop_column("skills", "source_payload")
    op.drop_column("skills", "metadata")
    op.drop_column("skills", "stats")
    op.drop_column("skills", "owner_handle")
    op.drop_column("skills", "source_url")
    op.drop_column("skills", "source_slug")
    op.drop_column("skills", "source")
    op.drop_column("skills", "display_name")
