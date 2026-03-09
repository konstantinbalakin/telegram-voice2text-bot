"""fix_duplicate_active_subscriptions

Revision ID: f9b400ff26ec
Revises: 2c2dfd6dd905
Create Date: 2026-03-05

Data migration: for users with multiple active subscriptions,
keep the most recent one and cancel all others.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision: str = "f9b400ff26ec"
down_revision: Union[str, None] = "2c2dfd6dd905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        sa.text(
            """
            UPDATE user_subscriptions
            SET status = 'cancelled', auto_renew = 0, updated_at = :now
            WHERE status = 'active'
              AND id NOT IN (
                SELECT keep_id FROM (
                  SELECT MAX(id) as keep_id
                  FROM user_subscriptions
                  WHERE status = 'active'
                  GROUP BY user_id
                  HAVING COUNT(*) > 1
                )
              )
              AND user_id IN (
                SELECT user_id
                FROM user_subscriptions
                WHERE status = 'active'
                GROUP BY user_id
                HAVING COUNT(*) > 1
              )
            """
        ),
        {"now": now},
    )


def downgrade() -> None:
    pass
