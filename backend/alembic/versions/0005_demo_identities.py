"""Persist the bounded demo identities used by the non-production API auth."""

import sqlalchemy as sa

from alembic import op

revision = "0005_demo_identities"
down_revision = "0004_reservation_agency_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("demo_identities"):
        return
    op.create_table(
        "demo_identities",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("agency_id", sa.String(100), sa.ForeignKey("agencies.id", ondelete="RESTRICT")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint(
            "role IN ('PASSENGER','AGENCY_AGENT','ADMIN','AIRPORT')", name="ck_demo_identity_role"
        ),
    )


def downgrade() -> None:
    op.drop_table("demo_identities")
