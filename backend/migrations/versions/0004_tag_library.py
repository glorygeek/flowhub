"""Add tag library tables

Revision ID: 0004_tag_library
Revises: 0003_skill_sync_columns
Create Date: 2026-03-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_tag_library"
down_revision: Union[str, None] = "0003_skill_sync_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tag_definitions",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="keyword"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="rule"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tag_definitions_id"), "tag_definitions", ["id"], unique=False)
    op.create_index(op.f("ix_tag_definitions_name"), "tag_definitions", ["name"], unique=True)
    op.create_index(op.f("ix_tag_definitions_category"), "tag_definitions", ["category"], unique=False)
    op.create_index(op.f("ix_tag_definitions_source"), "tag_definitions", ["source"], unique=False)

    op.create_table(
        "skill_tag_links",
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="rule"),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="high"),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "tag_id", "source", name="uq_skill_tag_source"),
    )
    op.create_index(op.f("ix_skill_tag_links_id"), "skill_tag_links", ["id"], unique=False)
    op.create_index(op.f("ix_skill_tag_links_skill_id"), "skill_tag_links", ["skill_id"], unique=False)
    op.create_index(op.f("ix_skill_tag_links_tag_id"), "skill_tag_links", ["tag_id"], unique=False)
    op.create_index(op.f("ix_skill_tag_links_source"), "skill_tag_links", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_skill_tag_links_source"), table_name="skill_tag_links")
    op.drop_index(op.f("ix_skill_tag_links_tag_id"), table_name="skill_tag_links")
    op.drop_index(op.f("ix_skill_tag_links_skill_id"), table_name="skill_tag_links")
    op.drop_index(op.f("ix_skill_tag_links_id"), table_name="skill_tag_links")
    op.drop_table("skill_tag_links")

    op.drop_index(op.f("ix_tag_definitions_source"), table_name="tag_definitions")
    op.drop_index(op.f("ix_tag_definitions_category"), table_name="tag_definitions")
    op.drop_index(op.f("ix_tag_definitions_name"), table_name="tag_definitions")
    op.drop_index(op.f("ix_tag_definitions_id"), table_name="tag_definitions")
    op.drop_table("tag_definitions")
