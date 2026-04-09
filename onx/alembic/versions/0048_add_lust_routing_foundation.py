"""add lust routing foundation

Revision ID: 0048_add_lust_routing_foundation
Revises: 0047_fix_lust_service_job_target_case
Create Date: 2026-04-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048_add_lust_routing_foundation"
down_revision = "0047_fix_lust_service_job_target_case"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    lust_columns = {item["name"] for item in inspector.get_columns("lust_services")}
    lust_indexes = {str(item["name"]) for item in inspector.get_indexes("lust_services")}
    if "role" not in lust_columns:
        op.add_column("lust_services", sa.Column("role", sa.String(length=32), nullable=False, server_default="standalone"))
    if "country_code" not in lust_columns:
        op.add_column("lust_services", sa.Column("country_code", sa.String(length=8), nullable=True))
    if "selection_weight" not in lust_columns:
        op.add_column("lust_services", sa.Column("selection_weight", sa.Integer(), nullable=False, server_default="100"))
    if op.f("ix_lust_services_role") not in lust_indexes:
        op.create_index(op.f("ix_lust_services_role"), "lust_services", ["role"], unique=False)
    if op.f("ix_lust_services_country_code") not in lust_indexes:
        op.create_index(op.f("ix_lust_services_country_code"), "lust_services", ["country_code"], unique=False)

    if "lust_egress_pools" not in inspector.get_table_names():
        op.create_table(
            "lust_egress_pools",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("selection_strategy", sa.String(length=32), nullable=False, server_default="hash"),
            sa.Column("members_json", sa.JSON(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_lust_egress_pools_name"), "lust_egress_pools", ["name"], unique=True)

    if "lust_gateway_route_maps" not in inspector.get_table_names():
        op.create_table(
            "lust_gateway_route_maps",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("gateway_service_id", sa.String(length=36), nullable=False),
            sa.Column("egress_pool_id", sa.String(length=36), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("destination_country_code", sa.String(length=8), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["gateway_service_id"], ["lust_services.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["egress_pool_id"], ["lust_egress_pools.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_lust_gateway_route_maps_name"), "lust_gateway_route_maps", ["name"], unique=True)
        op.create_index(op.f("ix_lust_gateway_route_maps_gateway_service_id"), "lust_gateway_route_maps", ["gateway_service_id"], unique=False)
        op.create_index(op.f("ix_lust_gateway_route_maps_egress_pool_id"), "lust_gateway_route_maps", ["egress_pool_id"], unique=False)
        op.create_index(op.f("ix_lust_gateway_route_maps_destination_country_code"), "lust_gateway_route_maps", ["destination_country_code"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "lust_gateway_route_maps" in inspector.get_table_names():
        for index_name in (
            op.f("ix_lust_gateway_route_maps_destination_country_code"),
            op.f("ix_lust_gateway_route_maps_egress_pool_id"),
            op.f("ix_lust_gateway_route_maps_gateway_service_id"),
            op.f("ix_lust_gateway_route_maps_name"),
        ):
            try:
                op.drop_index(index_name, table_name="lust_gateway_route_maps")
            except Exception:
                pass
        op.drop_table("lust_gateway_route_maps")

    if "lust_egress_pools" in inspector.get_table_names():
        try:
            op.drop_index(op.f("ix_lust_egress_pools_name"), table_name="lust_egress_pools")
        except Exception:
            pass
        op.drop_table("lust_egress_pools")

    lust_columns = {item["name"] for item in inspector.get_columns("lust_services")}
    lust_indexes = {str(item["name"]) for item in inspector.get_indexes("lust_services")}
    if op.f("ix_lust_services_country_code") in lust_indexes:
        op.drop_index(op.f("ix_lust_services_country_code"), table_name="lust_services")
    if op.f("ix_lust_services_role") in lust_indexes:
        op.drop_index(op.f("ix_lust_services_role"), table_name="lust_services")
    if "selection_weight" in lust_columns:
        op.drop_column("lust_services", "selection_weight")
    if "country_code" in lust_columns:
        op.drop_column("lust_services", "country_code")
    if "role" in lust_columns:
        op.drop_column("lust_services", "role")
