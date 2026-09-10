# Modelo de datos analítico

Este documento define el modelo lógico. Para el flujo completo, controles,
operación AWS y diagramas, consulte el
[Diseño detallado de la capa analítica](analytics-detailed-design.md).

Las migraciones `backend/alembic/versions/0006_analytics_schema.py` y
`0007_analytics_refresh.py` crean el schema
`analytics` dentro de la RDS independiente `airline_analytics`. Es una
capa de ingeniería de datos: conserva claves de origen para reconciliación y
prepara hechos dimensionales, pero no implementa dashboards ni métricas de
presentación.

## Contrato de tablas

| Tabla | Grano | Fuente OLTP principal | Uso futuro |
|---|---|---|---|
| `dim_date` | Una fila por fecha calendario | Derivada | Filtros temporales |
| `dim_route` | Un tramo programado operacional | `scheduled_legs`, `scheduled_flights` | Ocupación e ingresos por ruta |
| `dim_flight` | Una instancia de vuelo y fecha de servicio | `flight_instances`, `scheduled_flights` | Cortar hechos por vuelo |
| `dim_cabin` | Una cabina | `cabins` | Ocupación y tarifa |
| `dim_fare_band` | Banda de anticipación (0–6, 7–30, 31+ días) | `advance_multiplier`, fechas OLTP | Ingresos por tarifa/anticipación |
| `dim_channel` | Un canal de venta | `reservations.channel` | Comparar directo/agencia |
| `dim_agency` | Una agencia comercial | `agencies` | Atribución de ventas |
| `fact_sales_segment` | Un pasajero (`reservation_item`) en un tramo | `reservation_items`, `reservations`, `payments`, `refunds` | Ingreso aprobado, reembolso asignado e ingreso neto |
| `fact_reservation` | Una reserva | `reservations`, `audit_events` | Cancelaciones sin doble conteo multi-tramo |
| `bridge_reservation_route` | Una reserva en una ruta de su itinerario | `reservation_items`, `flight_leg_instances` | Cortar cancelaciones por ruta/fecha sin duplicar el hecho |
| `fact_leg_occupancy` | Un inventario tramo/cabina por snapshot ETL | `inventories`, `flight_leg_instances` | Capacidad y ocupación histórica |

Los hechos no copian nombres, apellidos, `actor_id`, `agent_id`, ni otros datos
de pasajeros. Tampoco se copia el `locator` operacional: `source_*_id` permite
trazabilidad y upsert sin exponer identificadores de reserva innecesarios.

## Reglas de carga

* Las dimensiones se cargan primero y se resuelven por clave natural; las
  claves surrogate `*_key` no se deben regenerar durante un upsert.
  `dim_route` usa un código legible de vuelo/secuencia/origen/destino (con un
  sufijo corto de lineage para evitar colisiones históricas) para
  resolver reimportaciones, pero conserva `source_route_id` como el
  `scheduled_leg_id` que define el grano operacional.
* `fact_sales_segment.source_reservation_item_id` y
  `fact_reservation.source_reservation_id` son claves idempotentes.
* `fact_sales_segment` guarda por separado `approved_revenue`,
  `refund_amount` (reembolso asignado al ítem) y `net_revenue`; el ETL debe
  asignar un refund de reserva a sus ítems (por ejemplo, proporcionalmente al
  gross del ítem), y reconciliar sus sumas contra pagos aprobados y refunds del
  OLTP.
* `fact_leg_occupancy` conserva snapshots: la unicidad es
  `(source_inventory_id, snapshot_at)`, por lo que una actualización del
  inventario no borra el historial.
* `fact_reservation.cancellation_flag` solo se marca para estado
  `CANCELLED` respaldado por transición voluntaria; `EXPIRED` y
  `PAYMENT_FAILED` son estados distintos y no son cancelaciones.
  `previously_confirmed` identifica la cancelación voluntaria posterior a una
  confirmación. `bridge_reservation_route` permite filtrar por ruta y fecha de
  salida manteniendo el conteo de reservas en `fact_reservation`.
* Las fechas son role-playing: `booking_date_key`/`created_date_key` representa
  creación de reserva, `departure_date_key` representa salida del tramo o la
  primera salida del itinerario, y `cancellation_date_key` representa la
  transición a cancelada. Todas apuntan a `dim_date`; nunca se reutiliza una
  columna con semántica ambigua.
  En `fact_leg_occupancy`, `departure_date_key` representa específicamente la
  fecha operacional del tramo; no existe un `date_key` genérico duplicado.
* Los importes se mantienen en `numeric(14,2)` y COP por defecto. El ETL debe
  reconciliar ventas aprobadas y reembolsos antes de marcar `etl_run` como
  `SUCCEEDED`.
* `etl_run` registra cutoff, conteos y resultado de reconciliación; solo se
  actualiza `etl_watermark` después de una ejecución exitosa.
  Una ejecución exitosa hace inmutable el par `run_id`/`source_cutoff_at`:
  repetirlo devuelve no-op; reutilizar el `run_id` con otro snapshot falla.
  Los errores se revierten transaccionalmente; el caller de Glue debe persistir
  una auditoría `FAILED` fuera de la transacción si la necesita.

La migración es repetible (`IF NOT EXISTS`) y su `downgrade` elimina únicamente
el schema analítico. Las FK internas protegen la carga dimensional sin acoplar
el modelo a eliminaciones del OLTP.
