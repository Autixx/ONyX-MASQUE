"""add device certificates

Revision ID: 0044_add_device_certificates
Revises: 0043_add_lust_services
Create Date: 2026-03-29 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0044_add_device_certificates"
down_revision = "0043_add_lust_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_certificates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("serial_number_hex", sa.String(length=128), nullable=False),
        sa.Column("fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("subject_text", sa.String(length=255), nullable=False),
        sa.Column("certificate_pem", sa.Text(), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial_number_hex"),
        sa.UniqueConstraint("fingerprint_sha256"),
    )
    op.create_index(op.f("ix_device_certificates_device_id"), "device_certificates", ["device_id"], unique=False)
    op.create_index(op.f("ix_device_certificates_fingerprint_sha256"), "device_certificates", ["fingerprint_sha256"], unique=True)
    op.create_index(op.f("ix_device_certificates_not_after"), "device_certificates", ["not_after"], unique=False)
    op.create_index(op.f("ix_device_certificates_serial_number_hex"), "device_certificates", ["serial_number_hex"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_device_certificates_serial_number_hex"), table_name="device_certificates")
    op.drop_index(op.f("ix_device_certificates_not_after"), table_name="device_certificates")
    op.drop_index(op.f("ix_device_certificates_fingerprint_sha256"), table_name="device_certificates")
    op.drop_index(op.f("ix_device_certificates_device_id"), table_name="device_certificates")
    op.drop_table("device_certificates")
