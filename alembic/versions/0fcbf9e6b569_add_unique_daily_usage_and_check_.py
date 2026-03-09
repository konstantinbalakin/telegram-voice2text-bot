"""add unique_daily_usage_and_check_purchase_type

Revision ID: 0fcbf9e6b569
Revises: a1b2c3d4e5f6
Create Date: 2026-03-06

Phase 1: Critical Constraints
- UNIQUE constraint on daily_usage(user_id, date)
- CHECK constraint on purchases.purchase_type IN ('package', 'subscription')
- Remove redundant single-column index ix_daily_usage_user_id (covered by UNIQUE)
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0fcbf9e6b569"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add UNIQUE constraint on daily_usage(user_id, date)
    # This also removes the redundant single-column index on user_id
    with op.batch_alter_table("daily_usage", schema=None) as batch_op:
        batch_op.drop_index("ix_daily_usage_user_id")
        batch_op.create_unique_constraint("uq_daily_usage_user_date", ["user_id", "date"])

    # Add CHECK constraint on purchases.purchase_type
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_purchases_purchase_type",
            "purchase_type IN ('package', 'subscription')",
        )


def downgrade() -> None:
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.drop_constraint("ck_purchases_purchase_type", type_="check")

    with op.batch_alter_table("daily_usage", schema=None) as batch_op:
        batch_op.drop_constraint("uq_daily_usage_user_date", type_="unique")
        batch_op.create_index("ix_daily_usage_user_id", ["user_id"], unique=False)
