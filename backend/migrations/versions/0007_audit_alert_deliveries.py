"""Add audit alert delivery logs

Revision ID: 0007_audit_alert_deliveries
Revises: 0006_operator_change_logs
Create Date: 2026-03-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_audit_alert_deliveries"
down_revision: Union[str, None] = "0006_operator_change_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_alert_deliveries",
        sa.Column("telemetry_event_id", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("destination", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="failed"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(op.f("ix_audit_alert_deliveries_id"), "audit_alert_deliveries", ["id"], unique=False)
    op.create_index(
        op.f("ix_audit_alert_deliveries_telemetry_event_id"),
        "audit_alert_deliveries",
        ["telemetry_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_alert_deliveries_workflow_id"),
        "audit_alert_deliveries",
        ["workflow_id"],
        unique=False,
    )
    op.create_index(op.f("ix_audit_alert_deliveries_run_id"), "audit_alert_deliveries", ["run_id"], unique=False)
    op.create_index(op.f("ix_audit_alert_deliveries_status"), "audit_alert_deliveries", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_alert_deliveries_status"), table_name="audit_alert_deliveries")
    op.drop_index(op.f("ix_audit_alert_deliveries_run_id"), table_name="audit_alert_deliveries")
    op.drop_index(op.f("ix_audit_alert_deliveries_workflow_id"), table_name="audit_alert_deliveries")
    op.drop_index(op.f("ix_audit_alert_deliveries_telemetry_event_id"), table_name="audit_alert_deliveries")
    op.drop_index(op.f("ix_audit_alert_deliveries_id"), table_name="audit_alert_deliveries")
    op.drop_table("audit_alert_deliveries")
