# Evidencia de validación de ingeniería de datos

Fecha: 2026-09-10

Esta evidencia contiene resultados locales reproducibles y no afirma un
despliegue analítico en AWS.

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
- Sintaxis de todos los scripts Bash: correcta.
- Imagen `airline-api:analytics-validation`: construida correctamente.
- `git diff --check`: sin errores de whitespace.

La validación remota de CloudFormation, la creación de recursos Glue y la
ejecución del job/crawlers quedan pendientes de reactivar una sesión Learner
Lab. Las credenciales disponibles durante esta implementación devolvieron una
denegación explícita de Vocareum para CloudFormation y Glue. No se intentó
eludir esa restricción ni se registraron credenciales.
