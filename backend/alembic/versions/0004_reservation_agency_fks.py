"""Enforce reservation agency and agent referential integrity."""

from alembic import op

revision = "0004_reservation_agency_fks"
down_revision = "0003_operational_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_reservation_agency",
        "reservations",
        "agencies",
        ["agency_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.create_foreign_key(
        "fk_reservation_agent",
        "reservations",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS reservations DROP CONSTRAINT IF EXISTS fk_reservation_agent")
    op.execute("ALTER TABLE IF EXISTS reservations DROP CONSTRAINT IF EXISTS fk_reservation_agency")
