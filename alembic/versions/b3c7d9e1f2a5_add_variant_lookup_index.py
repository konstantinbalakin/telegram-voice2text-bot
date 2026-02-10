"""Add variant lookup composite index

Revision ID: b3c7d9e1f2a5
Revises: f0514e20f750
Create Date: 2026-02-10

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b3c7d9e1f2a5"
down_revision: Union[str, None] = "f0514e20f750"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("transcription_variants") as batch_op:
        batch_op.create_index(
            "ix_variant_lookup",
            ["usage_id", "mode", "length_level", "emoji_level", "timestamps_enabled"],
        )


def downgrade() -> None:
    with op.batch_alter_table("transcription_variants") as batch_op:
        batch_op.drop_index("ix_variant_lookup")
