"""add acme email to lust services

Revision ID: 0045_add_lust_service_acme_email
Revises: 0044_add_device_certificates
Create Date: 2026-03-30 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0045_add_lust_service_acme_email"
down_revision = "0044_add_device_certificates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lust_services", sa.Column("acme_email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("lust_services", "acme_email")
