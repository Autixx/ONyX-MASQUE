"""initial onx schema

Revision ID: 0001_initial_onx_schema
Revises:
Create Date: 2026-03-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial_onx_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "role",
            sa.Enum("GATEWAY", "RELAY", "EGRESS", "MIXED", name="node_role"),
            nullable=False,
        ),
        sa.Column("management_address", sa.String(length=255), nullable=False),
        sa.Column("ssh_host", sa.String(length=255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False),
        sa.Column("ssh_user", sa.String(length=64), nullable=False),
        sa.Column(
            "auth_type",
            sa.Enum("PASSWORD", "PRIVATE_KEY", name="node_auth_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("UNKNOWN", "REACHABLE", "DEGRADED", "OFFLINE", name="node_status"),
            nullable=False,
        ),
        sa.Column("os_family", sa.String(length=64), nullable=True),
        sa.Column("os_version", sa.String(length=64), nullable=True),
        sa.Column("kernel_version", sa.String(length=128), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_nodes_name"), "nodes", ["name"], unique=True)

    op.create_table(
        "node_secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "SSH_PASSWORD",
                "SSH_PRIVATE_KEY",
                "TRANSPORT_PRIVATE_KEY",
                name="node_secret_kind",
            ),
            nullable=False,
        ),
        sa.Column("secret_ref", sa.String(length=128), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secret_ref"),
    )
    op.create_index(op.f("ix_node_secrets_kind"), "node_secrets", ["kind"], unique=False)
    op.create_index(op.f("ix_node_secrets_node_id"), "node_secrets", ["node_id"], unique=False)
    op.create_index(op.f("ix_node_secrets_secret_ref"), "node_secrets", ["secret_ref"], unique=True)

    op.create_table(
        "node_capabilities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("capability_name", sa.String(length=64), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "capability_name", name="uq_node_capability_name"),
    )
    op.create_index(op.f("ix_node_capabilities_node_id"), "node_capabilities", ["node_id"], unique=False)

    op.create_table(
        "links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("driver_name", sa.String(length=64), nullable=False),
        sa.Column(
            "topology_type",
            sa.Enum(
                "P2P",
                "UPSTREAM",
                "RELAY",
                "BALANCER_MEMBER",
                "SERVICE_EDGE",
                name="link_topology_type",
            ),
            nullable=False,
        ),
        sa.Column("left_node_id", sa.String(length=36), nullable=False),
        sa.Column("right_node_id", sa.String(length=36), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "PLANNED",
                "VALIDATING",
                "APPLYING",
                "ACTIVE",
                "DEGRADED",
                "FAILED",
                "DELETED",
                name="link_state",
            ),
            nullable=False,
        ),
        sa.Column("desired_spec_json", sa.JSON(), nullable=False),
        sa.Column("applied_spec_json", sa.JSON(), nullable=True),
        sa.Column("health_summary_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["left_node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_link_name"),
    )
    op.create_index(op.f("ix_links_driver_name"), "links", ["driver_name"], unique=False)
    op.create_index(op.f("ix_links_name"), "links", ["name"], unique=False)

    op.create_table(
        "link_endpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("link_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("side", sa.Enum("LEFT", "RIGHT", name="link_side"), nullable=False),
        sa.Column("interface_name", sa.String(length=64), nullable=True),
        sa.Column("listen_port", sa.Integer(), nullable=True),
        sa.Column("address_v4", sa.String(length=64), nullable=True),
        sa.Column("address_v6", sa.String(length=128), nullable=True),
        sa.Column("mtu", sa.Integer(), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("public_key", sa.String(length=255), nullable=True),
        sa.Column("private_key_secret_ref", sa.String(length=255), nullable=True),
        sa.Column("rendered_config", sa.Text(), nullable=True),
        sa.Column("applied_state_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_id", "side", name="uq_link_endpoint_side"),
    )
    op.create_index(op.f("ix_link_endpoints_link_id"), "link_endpoints", ["link_id"], unique=False)
    op.create_index(op.f("ix_link_endpoints_node_id"), "link_endpoints", ["node_id"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "BOOTSTRAP",
                "DISCOVER",
                "VALIDATE",
                "RENDER",
                "APPLY",
                "DESTROY",
                "PROBE",
                "ROLLBACK",
                name="job_kind",
            ),
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sa.Enum("NODE", "LINK", "POLICY", "BALANCER", name="job_target_type"),
            nullable=False,
        ),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                "ROLLED_BACK",
                "CANCELLED",
                "DEAD",
                name="job_state",
            ),
            nullable=False,
        ),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default=sa.text("15")),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_step", sa.String(length=255), nullable=True),
        sa.Column("request_payload_json", sa.JSON(), nullable=False),
        sa.Column("result_payload_json", sa.JSON(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("worker_owner", sa.String(length=128), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_kind"), "jobs", ["kind"], unique=False)
    op.create_index(op.f("ix_jobs_target_type"), "jobs", ["target_type"], unique=False)
    op.create_index(op.f("ix_jobs_target_id"), "jobs", ["target_id"], unique=False)
    op.create_index(op.f("ix_jobs_state"), "jobs", ["state"], unique=False)
    op.create_index(op.f("ix_jobs_worker_owner"), "jobs", ["worker_owner"], unique=False)
    op.create_index(op.f("ix_jobs_lease_expires_at"), "jobs", ["lease_expires_at"], unique=False)
    op.create_index(op.f("ix_jobs_next_run_at"), "jobs", ["next_run_at"], unique=False)
    op.create_index(op.f("ix_jobs_cancel_requested"), "jobs", ["cancel_requested"], unique=False)

    op.create_table(
        "event_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("level", sa.Enum("INFO", "WARNING", "ERROR", name="event_level"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_event_logs_job_id"), "event_logs", ["job_id"], unique=False)
    op.create_index(op.f("ix_event_logs_entity_type"), "event_logs", ["entity_type"], unique=False)
    op.create_index(op.f("ix_event_logs_entity_id"), "event_logs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_event_logs_level"), "event_logs", ["level"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_event_logs_level"), table_name="event_logs")
    op.drop_index(op.f("ix_event_logs_entity_id"), table_name="event_logs")
    op.drop_index(op.f("ix_event_logs_entity_type"), table_name="event_logs")
    op.drop_index(op.f("ix_event_logs_job_id"), table_name="event_logs")
    op.drop_table("event_logs")

    op.drop_index(op.f("ix_jobs_cancel_requested"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_next_run_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_lease_expires_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_worker_owner"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_state"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_target_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_target_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_kind"), table_name="jobs")
    op.drop_table("jobs")

    op.drop_index(op.f("ix_link_endpoints_node_id"), table_name="link_endpoints")
    op.drop_index(op.f("ix_link_endpoints_link_id"), table_name="link_endpoints")
    op.drop_table("link_endpoints")

    op.drop_index(op.f("ix_links_name"), table_name="links")
    op.drop_index(op.f("ix_links_driver_name"), table_name="links")
    op.drop_table("links")

    op.drop_index(op.f("ix_node_capabilities_node_id"), table_name="node_capabilities")
    op.drop_table("node_capabilities")

    op.drop_index(op.f("ix_node_secrets_secret_ref"), table_name="node_secrets")
    op.drop_index(op.f("ix_node_secrets_node_id"), table_name="node_secrets")
    op.drop_index(op.f("ix_node_secrets_kind"), table_name="node_secrets")
    op.drop_table("node_secrets")

    op.drop_index(op.f("ix_nodes_name"), table_name="nodes")
    op.drop_table("nodes")
