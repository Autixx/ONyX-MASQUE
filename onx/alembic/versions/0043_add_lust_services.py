"""add lust services

Revision ID: 0043_add_lust_services
Revises: 0042_add_quick_deploy_sessions
Create Date: 2026-03-28 05:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0043_add_lust_services"
down_revision = "0042_add_quick_deploy_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "lust_services" not in inspector.get_table_names():
        op.create_table(
            "lust_services",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("node_id", sa.String(length=36), nullable=False),
            sa.Column("state", sa.String(length=32), nullable=False, server_default="planned"),
            sa.Column("listen_host", sa.String(length=255), nullable=False, server_default="0.0.0.0"),
            sa.Column("listen_port", sa.Integer(), nullable=False, server_default="443"),
            sa.Column("public_host", sa.String(length=255), nullable=False),
            sa.Column("public_port", sa.Integer(), nullable=True),
            sa.Column("tls_server_name", sa.String(length=255), nullable=True),
            sa.Column("h2_path", sa.String(length=255), nullable=False, server_default="/lust"),
            sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("auth_scheme", sa.String(length=32), nullable=False, server_default="bearer"),
            sa.Column("client_dns_resolver", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("desired_config_json", sa.JSON(), nullable=True),
            sa.Column("health_summary_json", sa.JSON(), nullable=True),
            sa.Column("last_error_text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        inspector = sa.inspect(bind)
    existing_lust_indexes = {str(item["name"]) for item in inspector.get_indexes("lust_services")}
    if op.f("ix_lust_services_name") not in existing_lust_indexes:
        op.create_index(op.f("ix_lust_services_name"), "lust_services", ["name"], unique=True)
    if op.f("ix_lust_services_node_id") not in existing_lust_indexes:
        op.create_index(op.f("ix_lust_services_node_id"), "lust_services", ["node_id"], unique=False)
    if op.f("ix_lust_services_state") not in existing_lust_indexes:
        op.create_index(op.f("ix_lust_services_state"), "lust_services", ["state"], unique=False)

    if bind.dialect.name == "sqlite":
        transport_columns = {str(item["name"]) for item in inspector.get_columns("transport_packages")}
        with op.batch_alter_table("transport_packages") as batch_op:
            if "preferred_lust_service_id" not in transport_columns:
                batch_op.add_column(sa.Column("preferred_lust_service_id", sa.String(length=36), nullable=True))
            if "lust_enabled" not in transport_columns:
                batch_op.add_column(sa.Column("lust_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        inspector = sa.inspect(bind)
        transport_indexes = {str(item["name"]) for item in inspector.get_indexes("transport_packages")}
        transport_fks = {str(item["name"]) for item in inspector.get_foreign_keys("transport_packages")}
        with op.batch_alter_table("transport_packages") as batch_op:
            if "fk_transport_packages_preferred_lust_service_id" not in transport_fks:
                batch_op.create_foreign_key(
                    "fk_transport_packages_preferred_lust_service_id",
                    "lust_services",
                    ["preferred_lust_service_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if op.f("ix_transport_packages_preferred_lust_service_id") not in transport_indexes:
                batch_op.create_index(
                    op.f("ix_transport_packages_preferred_lust_service_id"),
                    ["preferred_lust_service_id"],
                    unique=False,
                )

        peer_columns = {str(item["name"]) for item in inspector.get_columns("peers")}
        with op.batch_alter_table("peers") as batch_op:
            if "lust_service_id" not in peer_columns:
                batch_op.add_column(sa.Column("lust_service_id", sa.String(length=36), nullable=True))
        inspector = sa.inspect(bind)
        peer_indexes = {str(item["name"]) for item in inspector.get_indexes("peers")}
        peer_fks = {str(item["name"]) for item in inspector.get_foreign_keys("peers")}
        with op.batch_alter_table("peers") as batch_op:
            if "fk_peers_lust_service_id" not in peer_fks:
                batch_op.create_foreign_key(
                    "fk_peers_lust_service_id",
                    "lust_services",
                    ["lust_service_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if op.f("ix_peers_lust_service_id") not in peer_indexes:
                batch_op.create_index(op.f("ix_peers_lust_service_id"), ["lust_service_id"], unique=False)
    else:
        transport_columns = {str(item["name"]) for item in inspector.get_columns("transport_packages")}
        if "preferred_lust_service_id" not in transport_columns:
            op.add_column("transport_packages", sa.Column("preferred_lust_service_id", sa.String(length=36), nullable=True))
        if "lust_enabled" not in transport_columns:
            op.add_column("transport_packages", sa.Column("lust_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        inspector = sa.inspect(bind)
        transport_indexes = {str(item["name"]) for item in inspector.get_indexes("transport_packages")}
        transport_fks = {str(item["name"]) for item in inspector.get_foreign_keys("transport_packages")}
        if "fk_transport_packages_preferred_lust_service_id" not in transport_fks:
            op.create_foreign_key(
                "fk_transport_packages_preferred_lust_service_id",
                "transport_packages",
                "lust_services",
                ["preferred_lust_service_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if op.f("ix_transport_packages_preferred_lust_service_id") not in transport_indexes:
            op.create_index(
                op.f("ix_transport_packages_preferred_lust_service_id"),
                "transport_packages",
                ["preferred_lust_service_id"],
                unique=False,
            )

        peer_columns = {str(item["name"]) for item in inspector.get_columns("peers")}
        if "lust_service_id" not in peer_columns:
            op.add_column("peers", sa.Column("lust_service_id", sa.String(length=36), nullable=True))
        inspector = sa.inspect(bind)
        peer_indexes = {str(item["name"]) for item in inspector.get_indexes("peers")}
        peer_fks = {str(item["name"]) for item in inspector.get_foreign_keys("peers")}
        if "fk_peers_lust_service_id" not in peer_fks:
            op.create_foreign_key(
                "fk_peers_lust_service_id",
                "peers",
                "lust_services",
                ["lust_service_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if op.f("ix_peers_lust_service_id") not in peer_indexes:
            op.create_index(op.f("ix_peers_lust_service_id"), "peers", ["lust_service_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("peers") as batch_op:
            batch_op.drop_index(op.f("ix_peers_lust_service_id"))
            batch_op.drop_constraint("fk_peers_lust_service_id", type_="foreignkey")
            batch_op.drop_column("lust_service_id")

        with op.batch_alter_table("transport_packages") as batch_op:
            batch_op.drop_index(op.f("ix_transport_packages_preferred_lust_service_id"))
            batch_op.drop_constraint("fk_transport_packages_preferred_lust_service_id", type_="foreignkey")
            batch_op.drop_column("lust_enabled")
            batch_op.drop_column("preferred_lust_service_id")
    else:
        op.drop_index(op.f("ix_peers_lust_service_id"), table_name="peers")
        op.drop_constraint("fk_peers_lust_service_id", "peers", type_="foreignkey")
        op.drop_column("peers", "lust_service_id")

        op.drop_index(op.f("ix_transport_packages_preferred_lust_service_id"), table_name="transport_packages")
        op.drop_constraint("fk_transport_packages_preferred_lust_service_id", "transport_packages", type_="foreignkey")
        op.drop_column("transport_packages", "lust_enabled")
        op.drop_column("transport_packages", "preferred_lust_service_id")

    op.drop_index(op.f("ix_lust_services_state"), table_name="lust_services")
    op.drop_index(op.f("ix_lust_services_node_id"), table_name="lust_services")
    op.drop_index(op.f("ix_lust_services_name"), table_name="lust_services")
    op.drop_table("lust_services")
