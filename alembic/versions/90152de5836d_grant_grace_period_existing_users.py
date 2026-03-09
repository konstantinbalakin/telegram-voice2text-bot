"""grant_grace_period_existing_users

Revision ID: 90152de5836d
Revises: 82545f6e6097
Create Date: 2026-03-02 01:12:13.572346

Data migration: grant 60 perpetual bonus minutes to all existing users
as a grace period when billing system is first enabled.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision: str = "90152de5836d"
down_revision: Union[str, None] = "82545f6e6097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GRACE_PERIOD_MINUTES = 60.0
SOURCE_DESCRIPTION = "Grace period bonus"


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    # Get all existing user IDs
    users = conn.execute(sa.text("SELECT id FROM users")).fetchall()

    for (user_id,) in users:
        # Check if user already has a grace period bonus
        existing = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM user_minute_balances "
                "WHERE user_id = :user_id AND source_description = :source"
            ),
            {"user_id": user_id, "source": SOURCE_DESCRIPTION},
        ).scalar()

        if existing == 0:
            conn.execute(
                sa.text(
                    "INSERT INTO user_minute_balances "
                    "(user_id, balance_type, minutes_remaining, expires_at, "
                    "source_description, created_at, updated_at) "
                    "VALUES (:user_id, 'bonus', :minutes, NULL, :source, :now, :now)"
                ),
                {
                    "user_id": user_id,
                    "minutes": GRACE_PERIOD_MINUTES,
                    "source": SOURCE_DESCRIPTION,
                    "now": now,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM user_minute_balances WHERE source_description = :source"),
        {"source": SOURCE_DESCRIPTION},
    )
