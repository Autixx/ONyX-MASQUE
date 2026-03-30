"""fix lust_service job target enum case for existing PostgreSQL instances

Migration 0046 incorrectly added 'lust_service' (lowercase) to the
job_target_type enum, but the model uses values_callable=enum_names which
stores enum member names in UPPERCASE ('LUST_SERVICE').  This migration
adds the correct uppercase value for any instance that ran 0046 before the
fix, as well as for fresh installs where 0046 now adds the correct value
(the IF NOT EXISTS guard makes it safe in both cases).

Revision ID: 0047_fix_lust_service_job_target_case
Revises: 0046_add_lust_service_job_target
Create Date: 2026-03-30 15:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0047_fix_lust_service_job_target_case"
down_revision = "0046_add_lust_service_job_target"
branch_labels = None
depends_on = None


def _job_target_type_labels(bind) -> set[str]:
    rows = bind.execute(
        sa.text(
            """
            SELECT enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'job_target_type'
            """
        )
    )
    return {str(row[0]) for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    labels = _job_target_type_labels(bind)
    if "LUST_SERVICE" not in labels:
        op.execute("ALTER TYPE job_target_type ADD VALUE 'LUST_SERVICE'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted.
    pass
