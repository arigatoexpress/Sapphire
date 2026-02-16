"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-11-23 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("strategy", sa.String(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trades_timestamp"), "trades", ["timestamp"], unique=False)
    op.create_index(op.f("ix_trades_agent_id"), "trades", ["agent_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trades_agent_id"), table_name="trades")
    op.drop_index(op.f("ix_trades_timestamp"), table_name="trades")
    op.drop_table("trades")
