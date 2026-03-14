"""Add search policy rule table

Revision ID: 0005_search_policy_rules
Revises: 0004_tag_library
Create Date: 2026-03-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_search_policy_rules"
down_revision: Union[str, None] = "0004_tag_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_policy_rules",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("intent_key", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("score_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
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
    op.create_index(op.f("ix_search_policy_rules_id"), "search_policy_rules", ["id"], unique=False)
    op.create_index(op.f("ix_search_policy_rules_name"), "search_policy_rules", ["name"], unique=True)
    op.create_index(op.f("ix_search_policy_rules_intent_key"), "search_policy_rules", ["intent_key"], unique=False)
    op.create_index(op.f("ix_search_policy_rules_priority"), "search_policy_rules", ["priority"], unique=False)
    op.create_index(op.f("ix_search_policy_rules_active"), "search_policy_rules", ["active"], unique=False)

    search_policy_rules = sa.table(
        "search_policy_rules",
        sa.column("name", sa.String),
        sa.column("intent_key", sa.String),
        sa.column("description", sa.Text),
        sa.column("reason", sa.Text),
        sa.column("conditions", sa.JSON),
        sa.column("score_delta", sa.Float),
        sa.column("priority", sa.Integer),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        search_policy_rules,
        [
            {
                "name": "api_fetch_collector_boost",
                "intent_key": "api_fetch",
                "description": "Boost collector-style skills for API/data requests.",
                "reason": "Whitelisted for API/data collection intent.",
                "conditions": {"query_domain_scope": "any", "skill_capabilities_any": ["collector"]},
                "score_delta": 12.0,
                "priority": 100,
                "active": True,
            },
            {
                "name": "api_fetch_market_penalty",
                "intent_key": "api_fetch",
                "description": "Downgrade market-analysis skills for generic API/data requests.",
                "reason": "Blacklisted market-analysis skill for API/data request.",
                "conditions": {
                    "query_domain_scope": "non_equity",
                    "skill_domains_any": ["equity", "crypto"],
                },
                "score_delta": -10.0,
                "priority": 110,
                "active": True,
            },
            {
                "name": "customer_reply_presenter_boost",
                "intent_key": "customer_reply",
                "description": "Boost presenter-style skills for customer-facing replies.",
                "reason": "Whitelisted for customer-facing reply intent.",
                "conditions": {"query_domain_scope": "any", "skill_capabilities_any": ["presenter"]},
                "score_delta": 12.0,
                "priority": 100,
                "active": True,
            },
            {
                "name": "customer_reply_fetch_only_penalty",
                "intent_key": "customer_reply",
                "description": "Downgrade fetch-only skills when the user asks for a customer reply.",
                "reason": "Downgraded fetch-only skill for customer-facing reply request.",
                "conditions": {
                    "query_domain_scope": "any",
                    "skill_capabilities_any": ["collector"],
                    "skill_capabilities_none": ["presenter"],
                },
                "score_delta": -4.0,
                "priority": 110,
                "active": True,
            },
            {
                "name": "customer_reply_market_penalty",
                "intent_key": "customer_reply",
                "description": "Downgrade market-analysis skills for generic customer reply requests.",
                "reason": "Blacklisted market-analysis skill for generic customer reply request.",
                "conditions": {
                    "query_domain_scope": "non_equity",
                    "skill_domains_any": ["equity", "crypto"],
                },
                "score_delta": -8.0,
                "priority": 120,
                "active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_search_policy_rules_active"), table_name="search_policy_rules")
    op.drop_index(op.f("ix_search_policy_rules_priority"), table_name="search_policy_rules")
    op.drop_index(op.f("ix_search_policy_rules_intent_key"), table_name="search_policy_rules")
    op.drop_index(op.f("ix_search_policy_rules_name"), table_name="search_policy_rules")
    op.drop_index(op.f("ix_search_policy_rules_id"), table_name="search_policy_rules")
    op.drop_table("search_policy_rules")
