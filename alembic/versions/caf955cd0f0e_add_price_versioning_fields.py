"""add_price_versioning_fields

Revision ID: caf955cd0f0e
Revises: 1fd70818303e
Create Date: 2026-03-06

Phase 3: Price versioning - add valid_from/valid_to/user_id to
subscription_prices and minute_packages for time-based pricing
and personalized discounts.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "caf955cd0f0e"
down_revision: Union[str, None] = "1fd70818303e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add versioning fields to minute_packages
    with op.batch_alter_table("minute_packages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "valid_from",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("(datetime('now'))"),
            )
        )
        batch_op.add_column(sa.Column("valid_to", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_minute_packages_user_id", ["user_id"], unique=False)
        batch_op.create_foreign_key("fk_minute_packages_user_id", "users", ["user_id"], ["id"])

    # Add versioning fields to subscription_prices
    with op.batch_alter_table("subscription_prices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "valid_from",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("(datetime('now'))"),
            )
        )
        batch_op.add_column(sa.Column("valid_to", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_subscription_prices_user_id", ["user_id"], unique=False)
        batch_op.create_foreign_key("fk_subscription_prices_user_id", "users", ["user_id"], ["id"])

    # Backfill valid_from from created_at for existing rows
    op.execute(
        "UPDATE subscription_prices SET valid_from = created_at WHERE valid_from = datetime('now')"
    )
    op.execute(
        "UPDATE minute_packages SET valid_from = created_at WHERE valid_from = datetime('now')"
    )


def downgrade() -> None:
    with op.batch_alter_table("subscription_prices", schema=None) as batch_op:
        batch_op.drop_constraint("fk_subscription_prices_user_id", type_="foreignkey")
        batch_op.drop_index("ix_subscription_prices_user_id")
        batch_op.drop_column("user_id")
        batch_op.drop_column("valid_to")
        batch_op.drop_column("valid_from")

    with op.batch_alter_table("minute_packages", schema=None) as batch_op:
        batch_op.drop_constraint("fk_minute_packages_user_id", type_="foreignkey")
        batch_op.drop_index("ix_minute_packages_user_id")
        batch_op.drop_column("user_id")
        batch_op.drop_column("valid_to")
        batch_op.drop_column("valid_from")
