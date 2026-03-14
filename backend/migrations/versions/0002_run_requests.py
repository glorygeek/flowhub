"""Add run requests table

Revision ID: 0002_run_requests
Revises: 0001_initial
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_run_requests"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

execution_mode_enum = sa.Enum("local", "remote", name="execution_mode")


def upgrade() -> None:
    op.create_table(
        "run_requests",
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("targets", sa.JSON(), nullable=False),
        sa.Column("credential_descriptors", sa.JSON(), nullable=False),
        sa.Column("output_format", sa.String(length=32), nullable=False),
        sa.Column("execution_mode", execution_mode_enum, nullable=False),
        sa.Column("user_notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workflow_spec", sa.JSON(), nullable=False),
        sa.Column("planning_notes", sa.JSON(), nullable=False),
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
    op.create_index(op.f("ix_run_requests_id"), "run_requests", ["id"], unique=False)
    op.create_index(op.f("ix_run_requests_status"), "run_requests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_run_requests_status"), table_name="run_requests")
    op.drop_index(op.f("ix_run_requests_id"), table_name="run_requests")
    op.drop_table("run_requests")
