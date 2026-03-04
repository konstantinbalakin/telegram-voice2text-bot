"""populate billing descriptions

Revision ID: 2c2dfd6dd905
Revises: d02ab6c5efe0
Create Date: 2026-03-05

Populate description for subscription prices and minute packages.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c2dfd6dd905"
down_revision: Union[str, None] = "d02ab6c5efe0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Subscription prices: Pro tier
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'week'"
        ).bindparams(desc="Pro на неделю — 30 мин/день для транскрибации голосовых сообщений")
    )
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'month'"
        ).bindparams(desc="Pro на месяц — 30 мин/день для транскрибации голосовых сообщений")
    )
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET description = :desc "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro') "
            "AND period = 'year'"
        ).bindparams(
            desc="Pro на год — 30 мин/день для транскрибации голосовых сообщений. Лучшая цена!"
        )
    )

    # Minute packages
    op.execute(
        sa.text(
            "UPDATE minute_packages SET description = :desc WHERE name = '50 минут'"
        ).bindparams(desc="50 минут транскрибации — подойдёт, чтобы попробовать")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET description = :desc WHERE name = '100 минут'"
        ).bindparams(desc="100 минут транскрибации — хватит на пару недель активного использования")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET description = :desc WHERE name = '500 минут'"
        ).bindparams(desc="500 минут транскрибации — выгодный пакет для регулярного использования")
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET description = :desc WHERE name = '5000 минут'"
        ).bindparams(desc="5000 минут транскрибации — максимальный пакет по лучшей цене за минуту")
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE subscription_prices SET description = NULL "
            "WHERE tier_id = (SELECT id FROM subscription_tiers WHERE name = 'Pro')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE minute_packages SET description = NULL "
            "WHERE name IN ('50 минут', '100 минут', '500 минут', '5000 минут')"
        )
    )
