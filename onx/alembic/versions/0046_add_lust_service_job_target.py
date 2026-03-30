"""add lust service job target type

Revision ID: 0046_add_lust_service_job_target
Revises: 0045_add_lust_service_acme_email
Create Date: 2026-03-30 13:00:00.000000
"""

from alembic import op


revision = "0046_add_lust_service_job_target"
down_revision = "0045_add_lust_service_acme_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE job_target_type ADD VALUE IF NOT EXISTS 'lust_service'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted.
    pass
