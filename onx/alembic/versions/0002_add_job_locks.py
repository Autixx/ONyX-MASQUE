"""add job locks

Revision ID: 0002_add_job_locks
Revises: 0001_initial_onx_schema
Create Date: 2026-03-10 00:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_add_job_locks"
down_revision: Union[str, Sequence[str], None] = "0001_initial_onx_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_locks",
        sa.Column("lock_key", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("worker_owner", sa.String(length=128), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lock_key"),
    )
    op.create_index(op.f("ix_job_locks_target_type"), "job_locks", ["target_type"], unique=False)
    op.create_index(op.f("ix_job_locks_target_id"), "job_locks", ["target_id"], unique=False)
    op.create_index(op.f("ix_job_locks_job_id"), "job_locks", ["job_id"], unique=False)
    op.create_index(op.f("ix_job_locks_expires_at"), "job_locks", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_job_locks_expires_at"), table_name="job_locks")
    op.drop_index(op.f("ix_job_locks_job_id"), table_name="job_locks")
    op.drop_index(op.f("ix_job_locks_target_id"), table_name="job_locks")
    op.drop_index(op.f("ix_job_locks_target_type"), table_name="job_locks")
    op.drop_table("job_locks")
