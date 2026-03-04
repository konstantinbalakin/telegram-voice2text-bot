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


def upgrade() -> None:
    now = datetime.now(timezone.utc).isoformat()

    # Billing conditions (global defaults)
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO billing_conditions (key, value, user_id, valid_from, created_at) "
            "VALUES ('daily_free_minutes', '10', NULL, :now, :now)"
        ).bindparams(now=now)
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO billing_conditions (key, value, user_id, valid_from, created_at) "
            "VALUES ('welcome_bonus_minutes', '60', NULL, :now, :now)"
        ).bindparams(now=now)
    )
    # welcome_bonus_days NULL = no expiry (perpetual bonus)
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO billing_conditions (key, value, user_id, valid_from, created_at) "
            "VALUES ('welcome_bonus_days', NULL, NULL, :now, :now)"
        ).bindparams(now=now)
    )

    # Subscription tier: Pro
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_tiers "
            "(name, daily_limit_minutes, description, display_order, is_active, created_at) "
            "VALUES ('Pro', 30, 'Pro подписка: 30 минут в день', 1, 1, :now)"
        ).bindparams(now=now)
    )

    # Subscription prices for Pro (use subquery for tier_id)
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_prices "
            "(tier_id, period, amount_rub, amount_stars, description, is_active, created_at) "
            "VALUES ((SELECT id FROM subscription_tiers WHERE name = 'Pro'), "
            "'week', 99, 50, :desc, 1, :now)"
        ).bindparams(
            desc="Pro на неделю — 30 мин/день для транскрибации голосовых сообщений",
            now=now,
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_prices "
            "(tier_id, period, amount_rub, amount_stars, description, is_active, created_at) "
            "VALUES ((SELECT id FROM subscription_tiers WHERE name = 'Pro'), "
            "'month', 299, 150, :desc, 1, :now)"
        ).bindparams(
            desc="Pro на месяц — 30 мин/день для транскрибации голосовых сообщений",
            now=now,
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO subscription_prices "
            "(tier_id, period, amount_rub, amount_stars, description, is_active, created_at) "
            "VALUES ((SELECT id FROM subscription_tiers WHERE name = 'Pro'), "
            "'year', 2490, 1250, :desc, 1, :now)"
        ).bindparams(
            desc="Pro на год — 30 мин/день для транскрибации голосовых сообщений. Лучшая цена!",
            now=now,
        )
    )

    # Minute packages
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages "
            "(name, minutes, price_rub, price_stars, description, display_order, is_active, created_at) "
            "VALUES ('50 минут', 50, 149, 75, :desc, 1, 1, :now)"
        ).bindparams(
            desc="50 минут транскрибации — подойдёт, чтобы попробовать",
            now=now,
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages "
            "(name, minutes, price_rub, price_stars, description, display_order, is_active, created_at) "
            "VALUES ('100 минут', 100, 249, 125, :desc, 2, 1, :now)"
        ).bindparams(
            desc="100 минут транскрибации — хватит на пару недель активного использования",
            now=now,
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages "
            "(name, minutes, price_rub, price_stars, description, display_order, is_active, created_at) "
            "VALUES ('500 минут', 500, 999, 500, :desc, 3, 1, :now)"
        ).bindparams(
            desc="500 минут транскрибации — выгодный пакет для регулярного использования",
            now=now,
        )
    )
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO minute_packages "
            "(name, minutes, price_rub, price_stars, description, display_order, is_active, created_at) "
            "VALUES ('5000 минут', 5000, 4990, 2500, :desc, 4, 1, :now)"
        ).bindparams(
            desc="5000 минут транскрибации — максимальный пакет по лучшей цене за минуту",
            now=now,
        )
    )


def downgrade() -> None:
    # Remove seed data
    op.execute(
        sa.text(
            "DELETE FROM minute_packages WHERE name IN "
            "('50 минут', '100 минут', '500 минут', '5000 минут')"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM subscription_prices WHERE tier_id = "
            "(SELECT id FROM subscription_tiers WHERE name = 'Pro')"
        )
    )
    op.execute(sa.text("DELETE FROM subscription_tiers WHERE name = 'Pro'"))
    op.execute(
        sa.text(
            "DELETE FROM billing_conditions WHERE key IN "
            "('daily_free_minutes', 'welcome_bonus_minutes', 'welcome_bonus_days') "
            "AND user_id IS NULL"
        )
    )
