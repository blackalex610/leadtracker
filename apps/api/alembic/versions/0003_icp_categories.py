"""niche presets replaced by built-in ICP targets; lead categories with deal value

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_businesses_niche_key", table_name="businesses")
    op.alter_column("businesses", "niche_key", new_column_name="target_key")
    op.create_index("ix_businesses_target_key", "businesses", ["target_key"], unique=False)
    op.drop_table("niche_presets")

    op.add_column("businesses", sa.Column("lead_category", sa.String(length=20), nullable=True))
    op.add_column("businesses", sa.Column("deal_value", sa.Integer(), server_default="0", nullable=False))
    op.add_column("businesses", sa.Column("close_odds", sa.SmallInteger(), server_default="0", nullable=False))
    op.add_column(
        "businesses", sa.Column("expected_value", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("businesses", sa.Column("category_reason", sa.Text(), nullable=True))
    op.add_column(
        "businesses",
        sa.Column(
            "category_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.create_index("ix_businesses_lead_category", "businesses", ["lead_category"], unique=False)
    op.create_index("ix_businesses_expected_value", "businesses", ["expected_value"], unique=False)
    # Search history is used to skip recently-run queries; old niche queries don't apply.
    op.create_index("ix_search_queries_text_query", "search_queries", ["text_query"], unique=False)
    op.execute("DELETE FROM app_settings WHERE key = 'seed_state'")


def downgrade() -> None:
    op.drop_index("ix_search_queries_text_query", table_name="search_queries")
    op.drop_index("ix_businesses_expected_value", table_name="businesses")
    op.drop_index("ix_businesses_lead_category", table_name="businesses")
    for column in (
        "category_details",
        "category_reason",
        "expected_value",
        "close_odds",
        "deal_value",
        "lead_category",
    ):
        op.drop_column("businesses", column)
    op.create_table(
        "niche_presets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("label_bg", sa.String(length=120), nullable=True),
        sa.Column("category_query", sa.String(length=200), nullable=False),
        sa.Column("included_type", sa.String(length=100), nullable=True),
        sa.Column("keywords", sa.String(length=300), nullable=True),
        sa.Column("match_types", postgresql.ARRAY(sa.String(length=100)), server_default="{}", nullable=False),
        sa.Column("calling_window_start", sa.String(length=5), nullable=True),
        sa.Column("calling_window_end", sa.String(length=5), nullable=True),
        sa.Column("booking_oriented", sa.Boolean(), nullable=False),
        sa.Column("discovery_dependent", sa.Boolean(), nullable=False),
        sa.Column(
            "strong_opportunities", postgresql.ARRAY(sa.String(length=40)), server_default="{}", nullable=False
        ),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_niche_presets")),
        sa.UniqueConstraint("key", name=op.f("uq_niche_presets_key")),
    )
    op.drop_index("ix_businesses_target_key", table_name="businesses")
    op.alter_column("businesses", "target_key", new_column_name="niche_key")
    op.create_index("ix_businesses_niche_key", "businesses", ["niche_key"], unique=False)
