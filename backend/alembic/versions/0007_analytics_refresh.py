"""Add the set-based, idempotent OLTP-to-analytics refresh function."""

from alembic import op

revision = "0007_analytics_refresh"
down_revision = "0006_analytics_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION analytics.refresh_warehouse(
    p_run_id uuid,
    p_snapshot_at timestamptz
) RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = analytics, public
AS $function$
DECLARE
    v_cutoff timestamptz := p_snapshot_at;
    v_approved_source numeric(14,2);
    v_refund_source numeric(14,2);
    v_approved_allocated numeric(14,2);
    v_refund_allocated numeric(14,2);
    v_existing_cutoff timestamptz;
    v_existing_status varchar(16);
    v_target_reservations integer;
    v_target_sales integer;
    v_target_occupancy integer;
    v_source_reservations integer;
    v_source_sales integer;
    v_source_occupancy integer;
    v_source_approved numeric(14,2);
    v_source_refund numeric(14,2);
    v_target_approved numeric(14,2);
    v_target_refund numeric(14,2);
BEGIN
    IF p_run_id IS NULL OR p_snapshot_at IS NULL THEN
      RAISE EXCEPTION 'run_id and snapshot_at are required';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('analytics.refresh_warehouse'));

    SELECT source_cutoff_at, status INTO v_existing_cutoff, v_existing_status
      FROM analytics.etl_run WHERE run_id = p_run_id;
    IF FOUND AND v_existing_status = 'SUCCEEDED' THEN
      IF v_existing_cutoff IS DISTINCT FROM p_snapshot_at THEN
        RAISE EXCEPTION 'run_id % is immutable and already succeeded at snapshot %', p_run_id, v_existing_cutoff;
      END IF;
      RETURN;
    END IF;
    IF FOUND AND v_existing_cutoff IS DISTINCT FROM p_snapshot_at THEN
      RAISE EXCEPTION 'run_id % was previously used with a different snapshot', p_run_id;
    END IF;
    INSERT INTO analytics.etl_run(run_id, pipeline_name, started_at, source_cutoff_at, status)
    VALUES (p_run_id, 'warehouse_refresh', clock_timestamp(), v_cutoff, 'RUNNING')
    ON CONFLICT (run_id) DO UPDATE
       SET source_cutoff_at = EXCLUDED.source_cutoff_at, status = 'RUNNING', error_message = NULL;

    -- Dimensions are loaded before facts. A scheduled leg is the operational
    -- route grain: this avoids collapsing two different legs with equal IATA
    -- endpoints and keeps the source scheduled_leg_id for lineage.
    INSERT INTO analytics.dim_route(source_route_id, route_code, origin, destination)
    SELECT sl.id, 'FL-' || sf.number || '-L' || sl.sequence::text || '-' || sl.origin || '-' || sl.destination
           || '-' || left(sl.id::text, 8),
           sl.origin, sl.destination
    FROM public.scheduled_legs sl
    JOIN public.scheduled_flights sf ON sf.id = sl.scheduled_flight_id
    ON CONFLICT (source_route_id) DO UPDATE SET
      route_code = EXCLUDED.route_code, origin = EXCLUDED.origin, destination = EXCLUDED.destination;

    INSERT INTO analytics.dim_flight(source_flight_instance_id, source_scheduled_flight_id,
                                     flight_number, service_date, flight_state)
    SELECT fi.id, fi.scheduled_flight_id, sf.number, fi.service_date::date, fi.state
    FROM public.flight_instances fi
    JOIN public.scheduled_flights sf ON sf.id = fi.scheduled_flight_id
    ON CONFLICT (source_flight_instance_id) DO UPDATE SET
      source_scheduled_flight_id = EXCLUDED.source_scheduled_flight_id,
      flight_number = EXCLUDED.flight_number, service_date = EXCLUDED.service_date,
      flight_state = EXCLUDED.flight_state;

    INSERT INTO analytics.dim_cabin(cabin_code, display_name)
    SELECT c.code, c.display_name FROM public.cabins c
    ON CONFLICT (cabin_code) DO UPDATE SET display_name = EXCLUDED.display_name;
    INSERT INTO analytics.dim_cabin(cabin_code, display_name)
    SELECT x.cabin, x.cabin FROM public.inventories x
    ON CONFLICT (cabin_code) DO NOTHING;

    INSERT INTO analytics.dim_channel(channel_code)
    SELECT DISTINCT r.channel FROM public.reservations r
    ON CONFLICT (channel_code) DO NOTHING;
    INSERT INTO analytics.dim_agency(source_agency_id, agency_name, active)
    SELECT a.id, a.name, a.active FROM public.agencies a
    ON CONFLICT (source_agency_id) DO UPDATE SET agency_name = EXCLUDED.agency_name, active = EXCLUDED.active;

    INSERT INTO analytics.dim_fare_band(fare_band_code, min_days_before_departure, max_days_before_departure)
    VALUES ('ADV_0_6', 0, 6), ('ADV_7_30', 7, 30), ('ADV_31_PLUS', 31, NULL)
    ON CONFLICT (fare_band_code) DO UPDATE SET
      min_days_before_departure = EXCLUDED.min_days_before_departure,
      max_days_before_departure = EXCLUDED.max_days_before_departure;

    INSERT INTO analytics.dim_date(date_key, calendar_date, year, quarter, month,
                                   week_of_year, day_of_month, day_of_week)
    SELECT to_char(d::date, 'YYYYMMDD')::integer, d::date,
           extract(year from d)::smallint, extract(quarter from d)::smallint,
           extract(month from d)::smallint, extract(week from d)::smallint,
           extract(day from d)::smallint, extract(isodow from d)::smallint
    FROM generate_series(
      LEAST(COALESCE((SELECT min(created_at::date) FROM public.reservations), v_cutoff::date), v_cutoff::date),
      GREATEST(COALESCE((SELECT max(departure_at::date) FROM public.flight_leg_instances), v_cutoff::date), v_cutoff::date),
      interval '1 day'
    ) d
    ON CONFLICT (date_key) DO NOTHING;

    CREATE TEMP TABLE tmp_sales ON COMMIT DROP AS
    WITH item_base AS (
      SELECT ri.id item_id, ri.reservation_id, ri.flight_leg_instance_id, ri.sequence,
             ri.base_fare, ri.airport_fee, ri.tax, ri.total item_total, ri.commission,
             ri.resource_state, r.state reservation_state, r.created_at booking_at,
             r.channel, r.agency_id, inv.cabin, fli.departure_at, fli.scheduled_leg_id,
             fli.flight_instance_id,
             GREATEST(r.created_at,
               COALESCE((SELECT max(x.created_at) FROM public.payments x WHERE x.reservation_id = r.id), r.created_at),
               COALESCE((SELECT max(x.created_at) FROM public.refunds x WHERE x.reservation_id = r.id), r.created_at),
               COALESCE((SELECT max(x.created_at) FROM public.audit_events x
                         WHERE x.entity_id = r.id::text AND x.entity_type = 'reservation'), r.created_at)) source_updated_at,
             COALESCE((SELECT sum(p.amount) FROM public.payments p
                       WHERE p.reservation_id = r.id AND p.state = 'APPROVED'), 0) approved_total,
             COALESCE((SELECT sum(f.amount) FROM public.refunds f
                       WHERE f.reservation_id = r.id), 0) refund_total,
             sum(ri.total) OVER (PARTITION BY ri.reservation_id) reservation_items_total,
             row_number() OVER (PARTITION BY ri.reservation_id ORDER BY ri.sequence DESC, ri.id DESC) last_item
      FROM public.reservation_items ri
      JOIN public.reservations r ON r.id = ri.reservation_id
      JOIN public.flight_leg_instances fli ON fli.id = ri.flight_leg_instance_id
      JOIN public.inventories inv ON inv.id = ri.inventory_id
    ), rounded AS (
      SELECT b.*,
             round(b.approved_total * b.item_total / NULLIF(b.reservation_items_total, 0), 2) approved_piece,
             round(b.refund_total * b.item_total / NULLIF(b.reservation_items_total, 0), 2) refund_piece_raw
      FROM item_base b
    ), allocated AS (
      SELECT x.*,
             CASE WHEN x.last_item = 1 THEN x.approved_total -
               COALESCE(sum(x.approved_piece) FILTER (WHERE x.last_item <> 1)
                 OVER (PARTITION BY x.reservation_id), 0) ELSE x.approved_piece END approved_piece_exact,
             CASE WHEN x.last_item = 1 THEN x.refund_total -
               COALESCE(sum(x.refund_piece_raw) FILTER (WHERE x.last_item <> 1)
                 OVER (PARTITION BY x.reservation_id), 0) ELSE x.refund_piece_raw END refund_piece_exact
      FROM rounded x
    )
    SELECT * FROM allocated;

    INSERT INTO analytics.fact_reservation(
      source_reservation_id, created_date_key, channel_key, agency_key,
      reservation_state, total_amount, commission_amount, cancellation_flag,
      cancellation_at, previously_confirmed, departure_date_key, cancellation_date_key,
      advance_days, source_updated_at
    )
    SELECT r.id, to_char(r.created_at::date, 'YYYYMMDD')::integer, ch.channel_key,
           ag.agency_key, r.state, r.total, r.commission, r.state = 'CANCELLED',
           cancel_evt.cancelled_at, COALESCE(cancel_evt.previously_confirmed, false),
           to_char(first_leg.departure_at::date, 'YYYYMMDD')::integer,
           to_char(cancel_evt.cancelled_at::date, 'YYYYMMDD')::integer,
           GREATEST(0, first_leg.departure_at::date - r.created_at::date),
           GREATEST(r.created_at, COALESCE(cancel_evt.cancelled_at, r.created_at),
                    COALESCE(activity.max_activity_at, r.created_at))
    FROM public.reservations r
    JOIN analytics.dim_channel ch ON ch.channel_code = r.channel
    LEFT JOIN analytics.dim_agency ag ON ag.source_agency_id = r.agency_id
    LEFT JOIN LATERAL (
      SELECT min(fli.departure_at) departure_at
      FROM public.reservation_items ri
      JOIN public.flight_leg_instances fli ON fli.id = ri.flight_leg_instance_id
      WHERE ri.reservation_id = r.id
    ) first_leg ON true
    LEFT JOIN LATERAL (
      SELECT min(ae.created_at) FILTER (WHERE ae.entity_type = 'reservation' AND ae.new_state = 'CANCELLED') cancelled_at,
             bool_or(ae.entity_type = 'reservation' AND ae.new_state = 'CONFIRMED') previously_confirmed
      FROM public.audit_events ae WHERE ae.entity_id = r.id::text
    ) cancel_evt ON true
    LEFT JOIN LATERAL (
      SELECT max(z.activity_at) max_activity_at FROM (
        SELECT max(x.created_at) activity_at FROM public.payments x WHERE x.reservation_id = r.id
        UNION ALL SELECT max(x.created_at) FROM public.refunds x WHERE x.reservation_id = r.id
        UNION ALL SELECT max(x.created_at) FROM public.audit_events x
          WHERE x.entity_id = r.id::text AND x.entity_type = 'reservation'
      ) z
    ) activity ON true
    ON CONFLICT (source_reservation_id) DO UPDATE SET
      created_date_key = EXCLUDED.created_date_key, channel_key = EXCLUDED.channel_key,
      agency_key = EXCLUDED.agency_key, reservation_state = EXCLUDED.reservation_state,
      total_amount = EXCLUDED.total_amount, commission_amount = EXCLUDED.commission_amount,
      cancellation_flag = EXCLUDED.cancellation_flag, cancellation_at = EXCLUDED.cancellation_at,
      previously_confirmed = EXCLUDED.previously_confirmed, departure_date_key = EXCLUDED.departure_date_key,
      cancellation_date_key = EXCLUDED.cancellation_date_key, advance_days = EXCLUDED.advance_days,
      source_updated_at = EXCLUDED.source_updated_at, loaded_at = clock_timestamp();

    INSERT INTO analytics.bridge_reservation_route(reservation_key, route_key, departure_date_key, route_sequence)
    SELECT fr.reservation_key, dr.route_key,
           to_char(min(fli.departure_at)::date, 'YYYYMMDD')::integer,
           min(ri.sequence)::smallint
    FROM public.reservation_items ri
    JOIN public.flight_leg_instances fli ON fli.id = ri.flight_leg_instance_id
    JOIN analytics.fact_reservation fr ON fr.source_reservation_id = ri.reservation_id
    JOIN analytics.dim_route dr ON dr.source_route_id = fli.scheduled_leg_id
    GROUP BY fr.reservation_key, dr.route_key
    ON CONFLICT (reservation_key, route_key) DO UPDATE SET
      departure_date_key = EXCLUDED.departure_date_key, route_sequence = EXCLUDED.route_sequence;

    INSERT INTO analytics.fact_sales_segment(
      source_reservation_item_id, source_reservation_id, booking_date_key,
      departure_date_key, route_key, flight_key, cabin_key, fare_band_key, channel_key,
      agency_key, reservation_state, resource_state, base_fare, airport_fee, tax,
      gross_amount, approved_revenue, refund_amount, commission_amount,
      advance_days, source_updated_at
    )
    SELECT s.item_id, s.reservation_id, to_char(s.booking_at::date, 'YYYYMMDD')::integer,
           to_char(s.departure_at::date, 'YYYYMMDD')::integer,
           dr.route_key, df.flight_key, dc.cabin_key,
           CASE WHEN GREATEST(0, s.departure_at::date - s.booking_at::date) < 7 THEN fb0.fare_band_key
                WHEN GREATEST(0, s.departure_at::date - s.booking_at::date) <= 30 THEN fb1.fare_band_key
                ELSE fb2.fare_band_key END,
           ch.channel_key, ag.agency_key, s.reservation_state, s.resource_state,
           s.base_fare, s.airport_fee, s.tax, s.item_total, s.approved_piece_exact,
           s.refund_piece_exact, s.commission, GREATEST(0, s.departure_at::date - s.booking_at::date), s.source_updated_at
    FROM tmp_sales s
    JOIN analytics.dim_route dr ON dr.source_route_id = s.scheduled_leg_id
    JOIN analytics.dim_flight df ON df.source_flight_instance_id = s.flight_instance_id
    JOIN analytics.dim_cabin dc ON dc.cabin_code = s.cabin
    JOIN analytics.dim_channel ch ON ch.channel_code = s.channel
    LEFT JOIN analytics.dim_agency ag ON ag.source_agency_id = s.agency_id
    JOIN analytics.dim_fare_band fb0 ON fb0.fare_band_code = 'ADV_0_6'
    JOIN analytics.dim_fare_band fb1 ON fb1.fare_band_code = 'ADV_7_30'
    JOIN analytics.dim_fare_band fb2 ON fb2.fare_band_code = 'ADV_31_PLUS'
    ON CONFLICT (source_reservation_item_id) DO UPDATE SET
      source_reservation_id = EXCLUDED.source_reservation_id,
      booking_date_key = EXCLUDED.booking_date_key, departure_date_key = EXCLUDED.departure_date_key,
      route_key = EXCLUDED.route_key, flight_key = EXCLUDED.flight_key,
      cabin_key = EXCLUDED.cabin_key,
      fare_band_key = EXCLUDED.fare_band_key, channel_key = EXCLUDED.channel_key,
      agency_key = EXCLUDED.agency_key, reservation_state = EXCLUDED.reservation_state,
      resource_state = EXCLUDED.resource_state, base_fare = EXCLUDED.base_fare,
      airport_fee = EXCLUDED.airport_fee, tax = EXCLUDED.tax,
      gross_amount = EXCLUDED.gross_amount,
      approved_revenue = EXCLUDED.approved_revenue, refund_amount = EXCLUDED.refund_amount,
      commission_amount = EXCLUDED.commission_amount, advance_days = EXCLUDED.advance_days,
      source_updated_at = EXCLUDED.source_updated_at, loaded_at = clock_timestamp();

    INSERT INTO analytics.fact_leg_occupancy(
      source_inventory_id, snapshot_at, departure_date_key, route_key, flight_key, cabin_key,
      capacity, held, confirmed
    )
    SELECT inv.id, p_snapshot_at, to_char(fli.departure_at::date, 'YYYYMMDD')::integer,
           dr.route_key, df.flight_key, dc.cabin_key, inv.capacity, inv.held, inv.confirmed
    FROM public.inventories inv
    JOIN public.flight_leg_instances fli ON fli.id = inv.flight_leg_instance_id
    JOIN analytics.dim_route dr ON dr.source_route_id = fli.scheduled_leg_id
    JOIN analytics.dim_flight df ON df.source_flight_instance_id = fli.flight_instance_id
    JOIN analytics.dim_cabin dc ON dc.cabin_code = inv.cabin
    ON CONFLICT (source_inventory_id, snapshot_at) DO UPDATE SET
      capacity = EXCLUDED.capacity, held = EXCLUDED.held, confirmed = EXCLUDED.confirmed,
      departure_date_key = EXCLUDED.departure_date_key, route_key = EXCLUDED.route_key,
      flight_key = EXCLUDED.flight_key, cabin_key = EXCLUDED.cabin_key,
      loaded_at = clock_timestamp();

    SELECT COALESCE(sum(p.amount), 0) INTO v_approved_source
      FROM public.payments p WHERE p.state = 'APPROVED';
    SELECT COALESCE(sum(f.amount), 0) INTO v_refund_source
      FROM public.refunds f;
    SELECT COALESCE(sum(approved_piece_exact), 0), COALESCE(sum(refund_piece_exact), 0)
      INTO v_approved_allocated, v_refund_allocated FROM tmp_sales;
    IF v_approved_source <> v_approved_allocated OR v_refund_source <> v_refund_allocated THEN
      RAISE EXCEPTION 'reconciliation mismatch: approved %/% refund %/%',
        v_approved_allocated, v_approved_source, v_refund_allocated, v_refund_source;
    END IF;
    SELECT count(*) INTO v_source_reservations FROM public.reservations;
    SELECT count(*) INTO v_source_sales FROM public.reservation_items;
    SELECT count(*) INTO v_source_occupancy FROM public.inventories;
    SELECT COALESCE(sum(p.amount), 0) INTO v_source_approved
      FROM public.payments p WHERE p.state = 'APPROVED';
    SELECT COALESCE(sum(f.amount), 0) INTO v_source_refund FROM public.refunds f;
    SELECT count(*) INTO v_target_reservations
      FROM analytics.fact_reservation f JOIN public.reservations r ON r.id = f.source_reservation_id;
    SELECT count(*) INTO v_target_sales
      FROM analytics.fact_sales_segment f JOIN public.reservation_items i ON i.id = f.source_reservation_item_id;
    SELECT count(*) INTO v_target_occupancy
      FROM analytics.fact_leg_occupancy WHERE snapshot_at = p_snapshot_at;
    SELECT COALESCE(sum(f.approved_revenue), 0), COALESCE(sum(f.refund_amount), 0)
      INTO v_target_approved, v_target_refund
      FROM analytics.fact_sales_segment f
      JOIN public.reservation_items i ON i.id = f.source_reservation_item_id;
    IF v_target_reservations <> v_source_reservations
       OR v_target_sales <> v_source_sales
       OR v_target_occupancy <> v_source_occupancy
       OR v_target_approved <> v_source_approved
       OR v_target_refund <> v_source_refund THEN
      RAISE EXCEPTION 'target reconciliation mismatch: counts %/%/% vs %/%/% and amounts %/% vs %/%',
        v_target_reservations, v_target_sales, v_target_occupancy,
        v_source_reservations, v_source_sales, v_source_occupancy,
        v_target_approved, v_target_refund, v_source_approved, v_source_refund;
    END IF;
    UPDATE analytics.etl_run SET finished_at = clock_timestamp(), status = 'SUCCEEDED',
      rows_extracted = v_source_reservations + v_source_sales + v_source_occupancy,
      rows_loaded = v_target_reservations + v_target_sales + v_target_occupancy,
      reconciliation = jsonb_build_object(
        'source_reservations', v_source_reservations,
        'target_reservations', v_target_reservations,
        'source_sales_items', v_source_sales,
        'target_sales_items', v_target_sales,
        'source_occupancy_rows', v_source_occupancy,
        'target_occupancy_rows', v_target_occupancy,
        'source_approved_revenue', v_source_approved,
        'target_approved_revenue', v_target_approved,
        'source_refund_amount', v_source_refund,
        'target_refund_amount', v_target_refund,
        'approved_delta', v_target_approved - v_source_approved,
        'refund_delta', v_target_refund - v_source_refund,
        'net_revenue', v_target_approved - v_target_refund
      ) WHERE run_id = p_run_id;
    INSERT INTO analytics.etl_watermark(pipeline_name, source_name, last_successful_cutoff_at, last_run_id)
    VALUES ('warehouse_refresh', 'public', v_cutoff, p_run_id)
    ON CONFLICT (pipeline_name) DO UPDATE SET
      last_successful_cutoff_at = EXCLUDED.last_successful_cutoff_at,
      last_run_id = EXCLUDED.last_run_id, updated_at = clock_timestamp();
EXCEPTION WHEN OTHERS THEN
    -- The function transaction rolls back on error. The Glue caller must
    -- persist a FAILED audit row outside this transaction if required.
    RAISE;
END;
$function$;
"""
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS analytics.refresh_warehouse(uuid, timestamptz)")
