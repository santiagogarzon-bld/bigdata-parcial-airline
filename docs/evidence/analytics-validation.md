# Evidencia de validación de ingeniería de datos

Fecha: 2026-09-10

## Validación AWS con RDS separadas

El stack `airline-demo` fue actualizado el 10 de septiembre de 2026 para usar
dos RDS PostgreSQL 16.10 privadas, `db.t3.micro`, Single-AZ y 20 GB gp3:
`airline_oltp` y `airline_analytics`. OLTP quedó en la migración
`0008_separate_analytics_database`, con 28 tablas `public` y sin schema
`analytics`; OLAP quedó con 13 tablas `analytics`, ninguna tabla operacional
en `public` y ningún foreign server persistente.

La primera carga entre instancias fue `SUCCEEDED` con 1.389 filas extraídas y
cargadas. La validación mediante el job Glue real también fue `SUCCEEDED` en
79 segundos: 1.406 filas extraídas/cargadas, `approved_delta=0.00` y
`refund_delta=0.00`. Los crawlers `airline-oltp-crawler` y
`airline-analytics-crawler` terminaron `SUCCEEDED`; publicaron respectivamente
12 fuentes OLTP autorizadas y 13 tablas OLAP. El trigger horario quedó
`ACTIVATED`. Después del cambio, `/api/v1/health` respondió correctamente y
la búsqueda BOG–MDE devolvió itinerarios, confirmando que el API continuó
usando OLTP.

La evidencia histórica local siguiente se conserva como referencia de pruebas.

## Base de datos y ETL

- Migración PostgreSQL desde `base` hasta `head`: correcta.
- Pruebas unitarias y API: `19 passed`.
- Integración PostgreSQL sin concurrencia: `21 passed`.
- Concurrencia real PostgreSQL: `2 passed`.
- Contrato y escenarios analíticos: `4 passed`.
- Runner ETL: `SUCCEEDED`, `106` registros extraídos, `106` cargados,
  `approved_delta=0.00` y `refund_delta=0.00`.
- Pruebas aisladas del runner ETL: `4 passed`.

Los escenarios analíticos cubren carga desde cero, hechos multi-tramo,
ingreso aprobado y neto, refund proporcional, cancelación posterior a compra,
cancelación pendiente, pago fallido, expiración, snapshot de ocupación,
reconciliación, idempotencia y rechazo de un `run_id` reutilizado con otro
snapshot.

## Calidad del repositorio e infraestructura

- Ruff: sin errores y 40 archivos con formato correcto.
- mypy estricto del backend: sin errores en 17 archivos.
- Validación positiva y negativa de infraestructura: correcta.
- Contrato del scheduler: trigger `SCHEDULED`, cron horario y activación segura
  posterior a la carga del artefacto.
- Sintaxis de todos los scripts Bash: correcta.
- Imagen `airline-api:analytics-validation`: construida correctamente.
- `git diff --check`: sin errores de whitespace.

La validación remota de CloudFormation, la creación de recursos Glue y la
ejecución del job/crawlers quedan pendientes de reactivar una sesión Learner
Lab. Las credenciales disponibles durante esta implementación devolvieron una
denegación explícita de Vocareum para CloudFormation y Glue. No se intentó
eludir esa restricción ni se registraron credenciales.
