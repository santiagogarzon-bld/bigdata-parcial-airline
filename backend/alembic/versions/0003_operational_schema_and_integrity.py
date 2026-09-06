"""Add operational catalogs, commercial history, and database integrity guards.

Revision ID: 0003_operational_schema
Revises: 0002_idempotency_window
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_operational_schema"
down_revision = "0002_idempotency_window"
branch_labels = None
depends_on = None

U = postgresql.UUID(as_uuid=False)
M = sa.Numeric(14, 2)


def _checked(table: str, name: str, expression: str) -> None:
    """Add and validate a guard, making incompatible legacy data fail loudly."""
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID")
    op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    # Legacy test fixtures used Base.metadata.create_all() before Alembic was
    # made authoritative. If that complete current schema is present while the
    # version table still says 0002, stamp the additive revision without trying
    # to recreate it. Normal deployed 0002 databases do not have this table.
    if sa.inspect(op.get_bind()).has_table("cabins"):
        return
    op.add_column("airports", sa.Column("name", sa.String(120), nullable=True))
    op.create_table(
        "cabins",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("display_name", sa.String(40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("sort_order > 0", name="ck_cabin_sort_order"),
    )
    op.create_table(
        "aircraft_types",
        sa.Column("id", U, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("manufacturer", sa.String(80), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "routes",
        sa.Column("id", U, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column(
            "origin",
            sa.String(3),
            sa.ForeignKey("airports.code", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "destination",
            sa.String(3),
            sa.ForeignKey("airports.code", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("origin <> destination", name="ck_route_distinct_airports"),
    )
    op.add_column("aircraft", sa.Column("aircraft_type_id", U, nullable=True))
    op.create_foreign_key(
        "fk_aircraft_type",
        "aircraft",
        "aircraft_types",
        ["aircraft_type_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.add_column("scheduled_flights", sa.Column("route_id", U, nullable=True))
    op.create_foreign_key(
        "fk_scheduled_flight_route",
        "scheduled_flights",
        "routes",
        ["route_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.create_table(
        "agencies",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "agency_id",
            sa.String(100),
            sa.ForeignKey("agencies.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "fare_rules",
        sa.Column("code", sa.String(40), primary_key=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("value", sa.Numeric(8, 4), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("value >= 0", name="ck_fare_rule_value_nonnegative"),
    )
    op.create_table(
        "operational_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(80), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
    )
    op.create_table(
        "itineraries",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "reservation_id",
            U,
            sa.ForeignKey("reservations.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "itinerary_segments",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "itinerary_id",
            U,
            sa.ForeignKey("itineraries.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "flight_leg_instance_id",
            U,
            sa.ForeignKey("flight_leg_instances.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.UniqueConstraint("itinerary_id", "sequence"),
        sa.UniqueConstraint("itinerary_id", "flight_leg_instance_id"),
        sa.CheckConstraint("sequence > 0", name="ck_itinerary_segment_sequence"),
    )
    op.create_table(
        "refunds",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "payment_id",
            U,
            sa.ForeignKey("payments.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "reservation_id",
            U,
            sa.ForeignKey("reservations.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", M, nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("amount >= 0", name="ck_refund_amount_nonnegative"),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", U, primary_key=True),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "actor_id", "idempotency_key", name="uq_idempotency_record"),
    )
    op.create_index(
        "ix_audit_events_entity_created", "audit_events", ["entity_type", "entity_id", "created_at"]
    )
    op.create_index("ix_payment_reservation_created", "payments", ["reservation_id", "created_at"])
    op.create_index(
        "ix_reservation_items_reservation_sequence",
        "reservation_items",
        ["reservation_id", "sequence"],
    )
    _checked("airports", "ck_airport_iata", "code ~ '^[A-Z]{3}$'")
    _checked("seats", "ck_seat_cabin", "cabin IN ('ECONOMY', 'BUSINESS')")
    _checked(
        "scheduled_legs",
        "ck_scheduled_leg_money",
        "base_economy >= 0 AND base_business >= 0 AND airport_fee >= 0",
    )
    _checked(
        "flight_instances",
        "ck_flight_instance_state",
        "state IN ('SCHEDULED', 'DELAYED', 'CANCELLED', 'COMPLETED')",
    )
    _checked("inventories", "ck_inventory_cabin", "cabin IN ('ECONOMY', 'BUSINESS')")
    _checked(
        "reservations",
        "ck_reservation_state",
        "state IN ('PENDING_PAYMENT', 'CONFIRMED', 'PAYMENT_FAILED', 'EXPIRED', 'CANCELLED')",
    )
    _checked("reservations", "ck_reservation_cabin", "cabin IN ('ECONOMY', 'BUSINESS')")
    _checked("reservations", "ck_reservation_channel", "channel IN ('DIRECT', 'AGENCY')")
    _checked("reservations", "ck_reservation_money_nonnegative", "total >= 0 AND commission >= 0")
    _checked(
        "reservation_items", "ck_reservation_item_state", "resource_state IN ('ACTIVE', 'RELEASED')"
    )
    _checked("reservation_items", "ck_reservation_item_sequence", "sequence > 0")
    _checked(
        "reservation_items",
        "ck_reservation_item_money_nonnegative",
        "base_fare >= 0 AND airport_fee >= 0 AND tax >= 0 AND total >= 0 AND commission >= 0",
    )
    _checked(
        "payments", "ck_payment_state", "state IN ('PENDING', 'APPROVED', 'DECLINED', 'REFUNDED')"
    )
    _checked("payments", "ck_payment_currency", "currency = 'COP'")
    _checked("payments", "ck_payment_amount_nonnegative", "amount >= 0")
    _checked("tickets", "ck_ticket_state", "state IN ('ISSUED', 'VOID')")
    _checked("coupons", "ck_coupon_state", "state IN ('ISSUED', 'VOID')")


def downgrade() -> None:
    # Additive catalog/history data is removed; original commercial rows stay.
    for index, table in (
        ("ix_audit_events_entity_created", "audit_events"),
        ("ix_payment_reservation_created", "payments"),
        ("ix_reservation_items_reservation_sequence", "reservation_items"),
    ):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index}"))
    for table, constraint in (
        ("coupons", "ck_coupon_state"),
        ("tickets", "ck_ticket_state"),
        ("payments", "ck_payment_amount_nonnegative"),
        ("payments", "ck_payment_currency"),
        ("payments", "ck_payment_state"),
        ("reservation_items", "ck_reservation_item_money_nonnegative"),
        ("reservation_items", "ck_reservation_item_sequence"),
        ("reservation_items", "ck_reservation_item_state"),
        ("reservations", "ck_reservation_money_nonnegative"),
        ("reservations", "ck_reservation_channel"),
        ("reservations", "ck_reservation_cabin"),
        ("reservations", "ck_reservation_state"),
        ("inventories", "ck_inventory_cabin"),
        ("flight_instances", "ck_flight_instance_state"),
        ("scheduled_legs", "ck_scheduled_leg_money"),
        ("seats", "ck_seat_cabin"),
        ("airports", "ck_airport_iata"),
    ):
        op.execute(sa.text(f"ALTER TABLE IF EXISTS {table} DROP CONSTRAINT IF EXISTS {constraint}"))
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
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    op.execute(
        sa.text("ALTER TABLE scheduled_flights DROP CONSTRAINT IF EXISTS fk_scheduled_flight_route")
    )
    op.execute(sa.text("ALTER TABLE scheduled_flights DROP COLUMN IF EXISTS route_id"))
    op.execute(sa.text("ALTER TABLE aircraft DROP CONSTRAINT IF EXISTS fk_aircraft_type"))
    op.execute(sa.text("ALTER TABLE aircraft DROP COLUMN IF EXISTS aircraft_type_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS routes CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS aircraft_types CASCADE"))
    op.execute(sa.text("ALTER TABLE airports DROP COLUMN IF EXISTS name"))
