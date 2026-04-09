"""add lust service maintenance mode

Revision ID: 0049_add_lust_service_maintenance_mode
Revises: 0048_add_lust_routing_foundation
Create Date: 2026-04-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_add_lust_service_maintenance_mode"
down_revision = "0048_add_lust_routing_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    lust_columns = {item["name"] for item in inspector.get_columns("lust_services")}
    if "maintenance_mode" not in lust_columns:
        op.add_column("lust_services", sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    lust_columns = {item["name"] for item in inspector.get_columns("lust_services")}
    if "maintenance_mode" in lust_columns:
        op.drop_column("lust_services", "maintenance_mode")
