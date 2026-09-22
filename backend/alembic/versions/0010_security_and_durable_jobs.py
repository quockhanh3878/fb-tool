"""Security boundaries, session rotation, durable jobs and delivery.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def upgrade():
    duplicate_chat = op.get_bind().execute(sa.text(
        "SELECT 1 FROM users WHERE telegram_chat_id IS NOT NULL "
        "GROUP BY telegram_chat_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate_chat:
        raise RuntimeError("Resolve duplicate Telegram account links before migration")
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("telegram_link_expires_at", sa.DateTime(timezone=True)))
        batch.create_unique_constraint("uq_users_telegram_chat", ["telegram_chat_id"])
    with op.batch_alter_table("comment_actions") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(64)))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch.create_unique_constraint("uq_comment_action_idempotency", ["idempotency_key"])
    with op.batch_alter_table("post_publishes") as batch:
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_comment_queue_due", "comment_actions", ["status", "scheduled_at"])
    op.create_index("ix_publish_queue_due", "post_publishes", ["status", "scheduled_at"])
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("amount_vnd", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("transaction_reference", sa.String(160), unique=True),
        sa.Column("confirmed_by", sa.String(32), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_table(
        "refresh_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_refresh_sessions_family_id", "refresh_sessions", ["family_id"])
    op.create_table(
        "resource_leases",
        sa.Column("resource", sa.String(160), primary_key=True),
        sa.Column("owner", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_resource_leases_expires_at", "resource_leases", ["expires_at"])
    op.create_table(
        "telegram_updates",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("dedup_key", sa.String(160), unique=True),
        sa.Column("chat_id", sa.String(64), nullable=False),
        sa.Column("bot_scope", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("post_id", sa.String(32), sa.ForeignKey("discovered_posts.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        *timestamps(),
    )
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])
    op.create_index("ix_notification_outbox_next_attempt_at", "notification_outbox", ["next_attempt_at"])


def downgrade():
    for table in ("notification_outbox", "telegram_updates", "resource_leases", "refresh_sessions", "payment_orders"):
        op.drop_table(table)
    op.drop_index("ix_publish_queue_due", table_name="post_publishes")
    op.drop_index("ix_comment_queue_due", table_name="comment_actions")
    with op.batch_alter_table("post_publishes") as batch:
        batch.drop_column("lease_expires_at")
    with op.batch_alter_table("comment_actions") as batch:
        batch.drop_constraint("uq_comment_action_idempotency", type_="unique")
        batch.drop_column("lease_expires_at")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_telegram_chat", type_="unique")
        batch.drop_column("telegram_link_expires_at")