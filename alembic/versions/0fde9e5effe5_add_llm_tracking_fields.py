"""add_llm_tracking_fields

Revision ID: 0fde9e5effe5
Revises: a9f3b2c8d1e4
Create Date: 2025-11-24 22:54:09.888058

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0fde9e5effe5"
down_revision: Union[str, None] = "a9f3b2c8d1e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add LLM tracking fields to usage table for hybrid mode."""
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("usage", schema=None) as batch_op:
        batch_op.add_column(sa.Column("llm_model", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("llm_processing_time_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove LLM tracking fields."""
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("usage", schema=None) as batch_op:
        batch_op.drop_column("llm_processing_time_seconds")
        batch_op.drop_column("llm_model")
