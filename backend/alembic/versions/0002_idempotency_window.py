"""Make idempotency uniqueness a renewable 24-hour operation scope.

Revision ID: 0002_idempotency_window
Revises: 0001_core_schema
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_idempotency_window"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("reservations")}
    if "idempotency_scope" not in columns:
        op.add_column(
            "reservations", sa.Column("idempotency_scope", sa.String(length=196), nullable=True)
        )
        op.execute("UPDATE reservations SET idempotency_scope = idempotency_key || ':' || id::text")
        op.alter_column("reservations", "idempotency_scope", nullable=False)
    constraints = {
        item["name"]: item["column_names"]
        for item in sa.inspect(bind).get_unique_constraints("reservations")
    }
    if constraints.get("uq_reservation_idempotency") != [
        "actor_id",
        "channel",
        "idempotency_scope",
    ]:
        if "uq_reservation_idempotency" in constraints:
            op.drop_constraint("uq_reservation_idempotency", "reservations", type_="unique")
        op.create_unique_constraint(
            "uq_reservation_idempotency",
            "reservations",
            ["actor_id", "channel", "idempotency_scope"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_reservation_idempotency", "reservations", type_="unique")
    op.create_unique_constraint(
        "uq_reservation_idempotency", "reservations", ["actor_id", "channel", "idempotency_key"]
    )
    op.drop_column("reservations", "idempotency_scope")
