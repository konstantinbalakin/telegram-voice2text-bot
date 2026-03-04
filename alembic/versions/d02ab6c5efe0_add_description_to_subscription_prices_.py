"""add description to subscription_prices and minute_packages

Revision ID: d02ab6c5efe0
Revises: c4d8f1a2b3e5
Create Date: 2026-03-05 01:04:25.789425

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d02ab6c5efe0"
down_revision: Union[str, None] = "c4d8f1a2b3e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("minute_packages", sa.Column("description", sa.String(length=500), nullable=True))
    op.add_column(
        "subscription_prices", sa.Column("description", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("subscription_prices", "description")
    op.drop_column("minute_packages", "description")
