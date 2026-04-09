"""add peer lust route override

Revision ID: 0050_add_peer_lust_route_override
Revises: 0049_add_lust_service_maintenance_mode
Create Date: 2026-04-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0050_add_peer_lust_route_override"
down_revision = "0049_add_lust_service_maintenance_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("peers")}
    if "lust_route_override_json" not in columns:
        op.add_column(
            "peers",
            sa.Column("lust_route_override_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("peers")}
    if "lust_route_override_json" in columns:
        op.drop_column("peers", "lust_route_override_json")
