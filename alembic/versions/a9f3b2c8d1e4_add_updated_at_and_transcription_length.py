"""add updated_at and transcription_length

Revision ID: a9f3b2c8d1e4
Revises: 7751fc657749
Create Date: 2025-10-29 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9f3b2c8d1e4'
down_revision: Union[str, None] = '7751fc657749'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add updated_at and transcription_length, make columns nullable, drop transcription_text."""

    # Add new columns
    op.add_column('usage', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column('usage', sa.Column('transcription_length', sa.Integer(), nullable=True))

    # Make existing columns nullable for staged writes
    op.alter_column('usage', 'voice_duration_seconds',
                    existing_type=sa.Integer(),
                    nullable=True)
    op.alter_column('usage', 'model_size',
                    existing_type=sa.String(length=50),
                    nullable=True)

    # Drop transcription_text column (privacy)
    op.drop_column('usage', 'transcription_text')


def downgrade() -> None:
    """Revert changes."""

    # Add back transcription_text
    op.add_column('usage', sa.Column('transcription_text', sa.Text(), nullable=False, server_default=''))

    # Make columns non-nullable again
    op.alter_column('usage', 'model_size',
                    existing_type=sa.String(length=50),
                    nullable=False)
    op.alter_column('usage', 'voice_duration_seconds',
                    existing_type=sa.Integer(),
                    nullable=False)

    # Drop new columns
    op.drop_column('usage', 'transcription_length')
    op.drop_column('usage', 'updated_at')
