"""cleanup_legacy_tables_and_fields

Revision ID: a1b2c3d4e5f6
Revises: f9b400ff26ec
Create Date: 2026-03-06

Drop legacy quota fields from users, drop transactions table,
drop language field from usage.
"""

from alembic import op
import sqlalchemy as sa
from datetime import date


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f9b400ff26ec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop 5 legacy quota fields from users
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("daily_quota_seconds")
        batch_op.drop_column("is_unlimited")
        batch_op.drop_column("today_usage_seconds")
        batch_op.drop_column("last_reset_date")
        batch_op.drop_column("total_usage_seconds")

    # Drop transactions table
    op.drop_table("transactions")

    # Drop language field from usage
    with op.batch_alter_table("usage") as batch_op:
        batch_op.drop_column("language")


def downgrade() -> None:
    # Restore language field on usage
    with op.batch_alter_table("usage") as batch_op:
        batch_op.add_column(sa.Column("language", sa.String(10), nullable=True))

    # Restore transactions table
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("quota_seconds_added", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("provider_transaction_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # Restore 5 legacy quota fields on users
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("daily_quota_seconds", sa.Integer(), server_default="60", nullable=False)
        )
        batch_op.add_column(
            sa.Column("is_unlimited", sa.Boolean(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("today_usage_seconds", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "last_reset_date",
                sa.Date(),
                server_default=str(date.today()),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("total_usage_seconds", sa.Integer(), server_default="0", nullable=False)
        )
