"""add_composite_indexes

Revision ID: 1fd70818303e
Revises: 0fcbf9e6b569
Create Date: 2026-03-06

Phase 2: Composite indexes for billing query optimization.
- billing_conditions(key, user_id, valid_from)
- user_subscriptions(user_id, status, expires_at)
- purchases(user_id, purchase_type, item_id, status)
- deduction_log(created_at) for future archiving
- Remove redundant single-column indexes covered by composites
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1fd70818303e"
down_revision: Union[str, None] = "0fcbf9e6b569"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # billing_conditions: composite replaces individual key + user_id indexes
    with op.batch_alter_table("billing_conditions", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_conditions_key")
        batch_op.drop_index("ix_billing_conditions_user_id")
        batch_op.create_index(
            "ix_billing_conditions_key_user_valid",
            ["key", "user_id", "valid_from"],
            unique=False,
        )

    # deduction_log: index for future archiving queries
    with op.batch_alter_table("deduction_log", schema=None) as batch_op:
        batch_op.create_index("ix_deduction_log_created", ["created_at"], unique=False)

    # purchases: composite replaces single user_id index
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.drop_index("ix_purchases_user_id")
        batch_op.create_index(
            "ix_purchases_user_type_item_status",
            ["user_id", "purchase_type", "item_id", "status"],
            unique=False,
        )

    # user_subscriptions: composite replaces single user_id index
    with op.batch_alter_table("user_subscriptions", schema=None) as batch_op:
        batch_op.drop_index("ix_user_subscriptions_user_id")
        batch_op.create_index(
            "ix_user_subscriptions_user_status_expires",
            ["user_id", "status", "expires_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("user_subscriptions", schema=None) as batch_op:
        batch_op.drop_index("ix_user_subscriptions_user_status_expires")
        batch_op.create_index("ix_user_subscriptions_user_id", ["user_id"], unique=False)

    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.drop_index("ix_purchases_user_type_item_status")
        batch_op.create_index("ix_purchases_user_id", ["user_id"], unique=False)

    with op.batch_alter_table("deduction_log", schema=None) as batch_op:
        batch_op.drop_index("ix_deduction_log_created")

    with op.batch_alter_table("billing_conditions", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_conditions_key_user_valid")
        batch_op.create_index("ix_billing_conditions_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_billing_conditions_key", ["key"], unique=False)
