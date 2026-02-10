"""add_original_file_path_to_usage

Revision ID: 4a34681766dc
Revises: 29b64c26ec8d
Create Date: 2025-12-08 15:26:22.271472

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4a34681766dc"
down_revision: Union[str, None] = "29b64c26ec8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add original_file_path field to usage table for retranscription support (Phase 8)."""
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("usage", schema=None) as batch_op:
        batch_op.add_column(sa.Column("original_file_path", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Remove original_file_path field."""
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("usage", schema=None) as batch_op:
        batch_op.drop_column("original_file_path")
