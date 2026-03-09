"""convert money fields to integer kopecks, add CHECK constraints, partial unique index

Revision ID: e7a1b2c3d4f5
Revises: caf955cd0f0e
Create Date: 2026-03-08 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7a1b2c3d4f5"
down_revision: Union[str, None] = "caf955cd0f0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Task 6.4: Convert money Float fields to Integer (kopecks) ---
    # SQLite does not support ALTER COLUMN, so we use batch mode.
    # Multiply data by 100 BEFORE type change so SQLite batch preserves correct values.

    # Step 1: Multiply existing ruble values by 100 (convert to kopecks)
    op.execute(
        sa.text("UPDATE subscription_prices SET amount_rub = CAST(amount_rub * 100 AS INTEGER)")
    )
    op.execute(sa.text("UPDATE minute_packages SET price_rub = CAST(price_rub * 100 AS INTEGER)"))
    op.execute(
        sa.text(
            "UPDATE purchases SET amount = CAST(amount * 100 AS INTEGER) WHERE currency = 'RUB'"
        )
    )

    # Step 2: Change column types Float → Integer
    with op.batch_alter_table("subscription_prices") as batch_op:
        batch_op.alter_column(
            "amount_rub",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    with op.batch_alter_table("minute_packages") as batch_op:
        batch_op.alter_column(
            "price_rub",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    with op.batch_alter_table("purchases") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    # --- Task 6.6: CHECK constraints ---
    with op.batch_alter_table("user_minute_balances") as batch_op:
        batch_op.create_check_constraint(
            "ck_user_minute_balances_minutes_remaining_non_negative",
            sa.column("minutes_remaining") >= 0,
        )

    with op.batch_alter_table("purchases") as batch_op:
        batch_op.create_check_constraint(
            "ck_purchases_amount_non_negative",
            sa.column("amount") >= 0,
        )

    with op.batch_alter_table("subscription_tiers") as batch_op:
        batch_op.create_check_constraint(
            "ck_subscription_tiers_daily_limit_positive",
            sa.column("daily_limit_minutes") > 0,
        )

    # --- Task 6.8: Partial unique index on active subscriptions ---
    op.create_index(
        "ix_user_subscriptions_unique_active",
        "user_subscriptions",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    # Drop partial unique index
    op.drop_index("ix_user_subscriptions_unique_active", table_name="user_subscriptions")

    # Remove CHECK constraints
    with op.batch_alter_table("subscription_tiers") as batch_op:
        batch_op.drop_constraint("ck_subscription_tiers_daily_limit_positive", type_="check")

    with op.batch_alter_table("purchases") as batch_op:
        batch_op.drop_constraint("ck_purchases_amount_non_negative", type_="check")

    with op.batch_alter_table("user_minute_balances") as batch_op:
        batch_op.drop_constraint(
            "ck_user_minute_balances_minutes_remaining_non_negative", type_="check"
        )

    # Revert Integer → Float
    with op.batch_alter_table("purchases") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )

    with op.batch_alter_table("minute_packages") as batch_op:
        batch_op.alter_column(
            "price_rub",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )

    with op.batch_alter_table("subscription_prices") as batch_op:
        batch_op.alter_column(
            "amount_rub",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )

    # Convert kopecks back to rubles
    op.execute(sa.text("UPDATE subscription_prices SET amount_rub = amount_rub / 100.0"))
    op.execute(sa.text("UPDATE minute_packages SET price_rub = price_rub / 100.0"))
    op.execute(sa.text("UPDATE purchases SET amount = amount / 100.0 WHERE currency = 'RUB'"))
