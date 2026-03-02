"""seed_billing_data

Revision ID: c4d8f1a2b3e5
Revises: 90152de5836d
Create Date: 2026-03-02 06:00:00.000000

Seed data: billing conditions, subscription tiers/prices, minute packages.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision: str = "c4d8f1a2b3e5"
down_revision: Union[str, None] = "90152de5836d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

now = datetime.now(timezone.utc).isoformat()


def upgrade() -> None:
    # Billing conditions (global defaults)
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO billing_conditions (key, value, user_id, valid_from, created_at) "
            f"VALUES ('daily_free_minutes', '10', NULL, '{now}', '{now}')"
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO billing_conditions (key, value, user_id, valid_from, created_at) "
            f"VALUES ('welcome_bonus_minutes', '60', NULL, '{now}', '{now}')"
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO billing_conditions (key, value, user_id, valid_from, created_at) "
            f"VALUES ('welcome_bonus_days', '', NULL, '{now}', '{now}')"
        )
    )

    # Subscription tier: Pro
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_tiers (name, daily_limit_minutes, description, display_order, is_active, created_at) "
            f"VALUES ('Pro', 30, 'Pro подписка: 30 минут в день', 1, 1, '{now}')"
        )
    )

    # Subscription prices for Pro (tier_id=1)
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_prices (tier_id, period, amount_rub, amount_stars, is_active, created_at) "
            f"VALUES (1, 'week', 99, 50, 1, '{now}')"
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_prices (tier_id, period, amount_rub, amount_stars, is_active, created_at) "
            f"VALUES (1, 'month', 299, 150, 1, '{now}')"
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_prices (tier_id, period, amount_rub, amount_stars, is_active, created_at) "
            f"VALUES (1, 'year', 2490, 1250, 1, '{now}')"
        )
    )

    # Minute packages
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages (name, minutes, price_rub, price_stars, display_order, is_active, created_at) "
            f"VALUES ('50 минут', 50, 149, 75, 1, 1, '{now}')"
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages (name, minutes, price_rub, price_stars, display_order, is_active, created_at) "
            f"VALUES ('100 минут', 100, 249, 125, 2, 1, '{now}')"
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages (name, minutes, price_rub, price_stars, display_order, is_active, created_at) "
            f"VALUES ('500 минут', 500, 999, 500, 3, 1, '{now}')"
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages (name, minutes, price_rub, price_stars, display_order, is_active, created_at) "
            f"VALUES ('5000 минут', 5000, 4990, 2500, 4, 1, '{now}')"
        )
    )


def downgrade() -> None:
    # Remove seed data
    op.execute(
        sa.text(
            "DELETE FROM minute_packages WHERE name IN ('50 минут', '100 минут', '500 минут', '5000 минут')"
        )
    )
    op.execute(sa.text("DELETE FROM subscription_prices WHERE tier_id = 1"))
    op.execute(sa.text("DELETE FROM subscription_tiers WHERE name = 'Pro'"))
    op.execute(
        sa.text(
            "DELETE FROM billing_conditions WHERE key IN ('daily_free_minutes', 'welcome_bonus_minutes', 'welcome_bonus_days') AND user_id IS NULL"
        )
    )
