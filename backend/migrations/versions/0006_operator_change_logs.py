"""Add operator change logs

Revision ID: 0006_operator_change_logs
Revises: 0005_search_policy_rules
Create Date: 2026-03-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_operator_change_logs"
down_revision: Union[str, None] = "0005_search_policy_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operator_change_logs",
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("before_state", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("after_state", sa.JSON(), nullable=False, server_default="{}"),
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
    op.create_index(op.f("ix_operator_change_logs_id"), "operator_change_logs", ["id"], unique=False)
    op.create_index(
        op.f("ix_operator_change_logs_entity_type"),
        "operator_change_logs",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operator_change_logs_entity_id"),
        "operator_change_logs",
        ["entity_id"],
        unique=False,
    )
    op.create_index(op.f("ix_operator_change_logs_action"), "operator_change_logs", ["action"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_operator_change_logs_action"), table_name="operator_change_logs")
    op.drop_index(op.f("ix_operator_change_logs_entity_id"), table_name="operator_change_logs")
    op.drop_index(op.f("ix_operator_change_logs_entity_type"), table_name="operator_change_logs")
    op.drop_index(op.f("ix_operator_change_logs_id"), table_name="operator_change_logs")
    op.drop_table("operator_change_logs")
