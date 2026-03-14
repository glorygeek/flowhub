"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

risk_level_enum = sa.Enum("low", "medium", "high", name="risk_level")
review_status_enum = sa.Enum(
    "draft", "pending", "approved", "rejected", "archived", name="review_status"
)
execution_mode_enum = sa.Enum("local", "remote", name="execution_mode")


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("execution_mode", execution_mode_enum, nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False),
        sa.Column("writes_external_state", sa.Boolean(), nullable=False),
        sa.Column("risk_level", risk_level_enum, nullable=False),
        sa.Column("status", review_status_enum, nullable=False),
        sa.Column("is_official", sa.Boolean(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
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
    op.create_index(op.f("ix_skills_id"), "skills", ["id"], unique=False)
    op.create_index(op.f("ix_skills_name"), "skills", ["name"], unique=True)

    op.create_table(
        "recipes",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("scenario", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("node_skeleton", sa.JSON(), nullable=False),
        sa.Column("edges", sa.JSON(), nullable=False),
        sa.Column("param_mappings", sa.JSON(), nullable=False),
        sa.Column("recommended_skill_categories", sa.JSON(), nullable=False),
        sa.Column("risk_level", risk_level_enum, nullable=False),
        sa.Column("status", review_status_enum, nullable=False),
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
    op.create_index(op.f("ix_recipes_id"), "recipes", ["id"], unique=False)
    op.create_index(op.f("ix_recipes_name"), "recipes", ["name"], unique=True)

    op.create_table(
        "workflows",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("edges", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("source_recipe_id", sa.Integer(), nullable=True),
        sa.Column("risk_level", risk_level_enum, nullable=False),
        sa.Column("status", review_status_enum, nullable=False),
        sa.Column("retry_policy", sa.JSON(), nullable=True),
        sa.Column("confirm_points", sa.JSON(), nullable=True),
        sa.Column("planner_decision_log", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["source_recipe_id"], ["recipes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflows_id"), "workflows", ["id"], unique=False)

    op.create_table(
        "telemetry_events",
        sa.Column("workflow_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("node_results", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("client_meta", sa.JSON(), nullable=False),
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
    op.create_index(op.f("ix_telemetry_events_id"), "telemetry_events", ["id"], unique=False)
    op.create_index(op.f("ix_telemetry_events_run_id"), "telemetry_events", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_telemetry_events_run_id"), table_name="telemetry_events")
    op.drop_index(op.f("ix_telemetry_events_id"), table_name="telemetry_events")
    op.drop_table("telemetry_events")

    op.drop_index(op.f("ix_workflows_id"), table_name="workflows")
    op.drop_table("workflows")

    op.drop_index(op.f("ix_recipes_name"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_id"), table_name="recipes")
    op.drop_table("recipes")

    op.drop_index(op.f("ix_skills_name"), table_name="skills")
    op.drop_index(op.f("ix_skills_id"), table_name="skills")
    op.drop_table("skills")

    execution_mode_enum.drop(op.get_bind(), checkfirst=False)
    review_status_enum.drop(op.get_bind(), checkfirst=False)
    risk_level_enum.drop(op.get_bind(), checkfirst=False)
