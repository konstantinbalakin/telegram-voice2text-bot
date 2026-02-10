"""add parent_usage_id to usage table

Revision ID: f0514e20f750
Revises: 4a34681766dc
Create Date: 2025-12-08 23:54:20.148687

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f0514e20f750"
down_revision: Union[str, None] = "4a34681766dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for foreign key constraints
    with op.batch_alter_table("usage", schema=None) as batch_op:
        # Add parent_usage_id column (nullable for existing records)
        batch_op.add_column(sa.Column("parent_usage_id", sa.Integer(), nullable=True))

        # Create index for faster parent lookups (if not exists)
        # Use index parameter in model definition will create index automatically
        # But we create it here explicitly for clarity
        batch_op.create_index("ix_usage_parent_usage_id", ["parent_usage_id"], unique=False)

        # Create foreign key constraint with CASCADE delete
        # If parent is deleted, children are also deleted
        batch_op.create_foreign_key(
            "fk_usage_parent_usage_id", "usage", ["parent_usage_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    # SQLite requires batch mode for foreign key constraints
    with op.batch_alter_table("usage", schema=None) as batch_op:
        # Drop foreign key constraint
        batch_op.drop_constraint("fk_usage_parent_usage_id", type_="foreignkey")

        # Drop index
        batch_op.drop_index("ix_usage_parent_usage_id")

        # Drop column
        batch_op.drop_column("parent_usage_id")
