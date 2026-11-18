"""add language to usage table

Revision ID: e8b7a6d5c4f3
Revises: b1c2d3e4f5a6
Create Date: 2026-11-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e8b7a6d5c4f3"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for schema changes
    with op.batch_alter_table("usage", schema=None) as batch_op:
        # Add language column (nullable for existing records)
        batch_op.add_column(sa.Column("language", sa.String(16), nullable=True))


def downgrade() -> None:
    # SQLite requires batch mode for schema changes
    with op.batch_alter_table("usage", schema=None) as batch_op:
        batch_op.drop_column("language")
