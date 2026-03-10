"""update subscription and package prices march 2026

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-11

Update prices and descriptions for subscription plans and minute packages.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "e7a1b2c3d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Subscription prices (amount_rub in kopecks) ---
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET amount_rub = :rub, amount_stars = :stars, description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'week'"
        ).bindparams(rub=8900, stars=40, desc="Неделя, чтобы попробовать")
    )
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET amount_rub = :rub, amount_stars = :stars, description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'month'"
        ).bindparams(rub=18000, stars=90, desc="Самый популярный период. 🏷 Скидка -53% от недельного")
    )
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET amount_rub = :rub, amount_stars = :stars, description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'year'"
        ).bindparams(rub=150000, stars=720, desc="Самое выгодное предложение. 🏷 Скидка -63% от недельного")
    )

    # --- Minute packages (price_rub in kopecks) ---
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '50 минут'"
        ).bindparams(rub=10000, stars=50, desc="Подойдёт, чтобы попробовать длинный файл.")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '100 минут'"
        ).bindparams(rub=17500, stars=85, desc="Подойдёт, чтобы попробовать длинный файл. 🏷 Скидка -13% от пакета на 50 минут")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '500 минут'"
        ).bindparams(rub=75000, stars=360, desc="Выгодное предложение. 🏷 Скидка -25% от пакета на 50 минут")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '5000 минут'"
        ).bindparams(rub=500000, stars=2400, desc="Максимальный пакет по лучшей цене за минуту. 🏷 Скидка -50% от пакета на 50 минут")
    )


def downgrade() -> None:
    # Restore previous subscription prices (converted to kopecks by e7a1b2c3d4f5)
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET amount_rub = :rub, amount_stars = :stars, description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'week'"
        ).bindparams(rub=9900, stars=50, desc="Pro на неделю — 30 мин/день для транскрибации голосовых сообщений")
    )
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET amount_rub = :rub, amount_stars = :stars, description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'month'"
        ).bindparams(rub=29900, stars=150, desc="Pro на месяц — 30 мин/день для транскрибации голосовых сообщений")
    )
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET amount_rub = :rub, amount_stars = :stars, description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'year'"
        ).bindparams(rub=249000, stars=1250, desc="Pro на год — 30 мин/день для транскрибации голосовых сообщений. Лучшая цена!")
    )

    # Restore previous minute package prices
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '50 минут'"
        ).bindparams(rub=14900, stars=75, desc="50 минут транскрибации — подойдёт, чтобы попробовать")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '100 минут'"
        ).bindparams(rub=24900, stars=125, desc="100 минут транскрибации — хватит на пару недель активного использования")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '500 минут'"
        ).bindparams(rub=99900, stars=500, desc="500 минут транскрибации — выгодный пакет для регулярного использования")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET price_rub = :rub, price_stars = :stars, description = :desc "
            "WHERE name = '5000 минут'"
        ).bindparams(rub=499000, stars=2500, desc="5000 минут транскрибации — максимальный пакет по лучшей цене за минуту")
    )
