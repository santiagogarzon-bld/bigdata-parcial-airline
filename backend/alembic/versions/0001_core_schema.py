"""Initial transactional airline core schema (explicit historical snapshot)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_core_schema"
down_revision = None
branch_labels = None
depends_on = None

U = postgresql.UUID(as_uuid=False)
M = sa.Numeric(14, 2)


def upgrade() -> None:
    # This must never import the live ORM: later tables belong to later revisions.
    op.create_table(
        "airports",
        sa.Column("code", sa.String(3), primary_key=True),
        sa.Column("iana_zone", sa.String(64), nullable=False),
    )
    op.create_table(
        "aircraft",
        sa.Column("id", U, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "scheduled_flights",
        sa.Column("id", U, primary_key=True),
        sa.Column("number", sa.String(10), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "seats",
        sa.Column("id", U, primary_key=True),
        sa.Column("aircraft_id", U, sa.ForeignKey("aircraft.id"), nullable=False),
        sa.Column("label", sa.String(8), nullable=False),
        sa.Column("cabin", sa.String(16), nullable=False),
        sa.UniqueConstraint("aircraft_id", "label"),
    )
    op.create_table(
        "scheduled_legs",
        sa.Column("id", U, primary_key=True),
        sa.Column("scheduled_flight_id", U, sa.ForeignKey("scheduled_flights.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(3), sa.ForeignKey("airports.code"), nullable=False),
        sa.Column("destination", sa.String(3), sa.ForeignKey("airports.code"), nullable=False),
        sa.Column("base_economy", M, nullable=False),
        sa.Column("base_business", M, nullable=False),
        sa.Column("airport_fee", M, nullable=False),
        sa.UniqueConstraint("scheduled_flight_id", "sequence"),
        sa.CheckConstraint("sequence > 0"),
        sa.CheckConstraint("origin <> destination"),
    )
    op.create_table(
        "flight_instances",
        sa.Column("id", U, primary_key=True),
        sa.Column("scheduled_flight_id", U, sa.ForeignKey("scheduled_flights.id"), nullable=False),
        sa.Column("aircraft_id", U, sa.ForeignKey("aircraft.id"), nullable=False),
        sa.Column("service_date", sa.String(10), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.UniqueConstraint("scheduled_flight_id", "service_date"),
    )
    op.create_table(
        "flight_leg_instances",
        sa.Column("id", U, primary_key=True),
        sa.Column("flight_instance_id", U, sa.ForeignKey("flight_instances.id"), nullable=False),
        sa.Column("scheduled_leg_id", U, sa.ForeignKey("scheduled_legs.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(3), sa.ForeignKey("airports.code"), nullable=False),
        sa.Column("destination", sa.String(3), sa.ForeignKey("airports.code"), nullable=False),
        sa.Column("departure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrival_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("flight_instance_id", "sequence"),
        sa.CheckConstraint("arrival_at > departure_at"),
    )
    op.create_table(
        "inventories",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "flight_leg_instance_id", U, sa.ForeignKey("flight_leg_instances.id"), nullable=False
        ),
        sa.Column("cabin", sa.String(16), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("held", sa.Integer(), nullable=False),
        sa.Column("confirmed", sa.Integer(), nullable=False),
        sa.UniqueConstraint("flight_leg_instance_id", "cabin"),
        sa.CheckConstraint(
            "capacity >= 0 AND held >= 0 AND confirmed >= 0 AND capacity >= held + confirmed",
            name="ck_inventory_nonnegative",
        ),
    )
    op.create_table(
        "reservations",
        sa.Column("id", U, primary_key=True),
        sa.Column("locator", sa.String(12), nullable=False, unique=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("cabin", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("agency_id", sa.String(100)),
        sa.Column("agent_id", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("total", M, nullable=False),
        sa.Column("commission", M, nullable=False),
        sa.UniqueConstraint(
            "actor_id", "channel", "idempotency_key", name="uq_reservation_idempotency"
        ),
        sa.CheckConstraint(
            "(channel <> 'AGENCY') OR (agency_id IS NOT NULL AND agent_id IS NOT NULL)",
            name="ck_agency_attribution",
        ),
    )
    op.create_table(
        "passengers",
        sa.Column("id", U, primary_key=True),
        sa.Column("reservation_id", U, sa.ForeignKey("reservations.id"), nullable=False),
        sa.Column("given_name", sa.String(100), nullable=False),
        sa.Column("surname", sa.String(100), nullable=False),
    )
    op.create_table(
        "reservation_items",
        sa.Column("id", U, primary_key=True),
        sa.Column("reservation_id", U, sa.ForeignKey("reservations.id"), nullable=False),
        sa.Column("passenger_id", U, sa.ForeignKey("passengers.id"), nullable=False),
        sa.Column(
            "flight_leg_instance_id", U, sa.ForeignKey("flight_leg_instances.id"), nullable=False
        ),
        sa.Column("inventory_id", U, sa.ForeignKey("inventories.id"), nullable=False),
        sa.Column("seat_id", U, sa.ForeignKey("seats.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("resource_state", sa.String(16), nullable=False),
        sa.Column("base_fare", M, nullable=False),
        sa.Column("advance_multiplier", sa.Numeric(5, 2), nullable=False),
        sa.Column("cabin_multiplier", sa.Numeric(5, 2), nullable=False),
        sa.Column("airport_fee", M, nullable=False),
        sa.Column("tax", M, nullable=False),
        sa.Column("total", M, nullable=False),
        sa.Column("commission", M, nullable=False),
        sa.UniqueConstraint("passenger_id", "flight_leg_instance_id"),
    )
    op.create_index(
        "uq_active_seat_assignment",
        "reservation_items",
        ["flight_leg_instance_id", "seat_id"],
        unique=True,
        postgresql_where=sa.text("resource_state = 'ACTIVE'"),
    )
    op.create_table(
        "payments",
        sa.Column("id", U, primary_key=True),
        sa.Column("reservation_id", U, sa.ForeignKey("reservations.id"), nullable=False),
        sa.Column("operation_reference", sa.String(128), nullable=False, unique=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("amount", M, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "tickets",
        sa.Column("id", U, primary_key=True),
        sa.Column("reservation_id", U, sa.ForeignKey("reservations.id"), nullable=False),
        sa.Column("passenger_id", U, sa.ForeignKey("passengers.id"), nullable=False),
        sa.Column("number", sa.String(30), nullable=False, unique=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("reservation_id", "passenger_id"),
    )
    op.create_table(
        "coupons",
        sa.Column("id", U, primary_key=True),
        sa.Column("ticket_id", U, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column(
            "flight_leg_instance_id", U, sa.ForeignKey("flight_leg_instances.id"), nullable=False
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.UniqueConstraint("ticket_id", "flight_leg_instance_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", U, primary_key=True),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(40), nullable=False),
        sa.Column("old_state", sa.String(32)),
        sa.Column("new_state", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("data", postgresql.JSON(astext_type=sa.Text()), nullable=False),
    )


def downgrade() -> None:
    # This also cleans tables created by legacy create_all test fixtures.
    for table in (
        "idempotency_records",
        "refunds",
        "itinerary_segments",
        "itineraries",
        "operational_settings",
        "fare_rules",
        "agents",
        "agencies",
        "cabins",
        "routes",
        "aircraft_types",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    for table in (
        "audit_events",
        "coupons",
        "tickets",
        "payments",
        "reservation_items",
        "passengers",
        "reservations",
        "inventories",
        "flight_leg_instances",
        "flight_instances",
        "scheduled_legs",
        "seats",
        "scheduled_flights",
        "aircraft",
        "airports",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
