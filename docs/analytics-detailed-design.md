# Diseño detallado de la capa analítica

## 1. Objetivo y alcance

Esta fase prepara una base confiable, trazable y operable para análisis
posteriores. Implementa ingeniería de datos: modelo dimensional, ETL horario,
catálogo, seguridad, calidad, reconciliación y operación en AWS. No implementa
dashboards, indicadores de negocio, visualizaciones, modelos predictivos ni
interpretación de resultados.

La solución conserva Amazon RDS PostgreSQL como fuente de verdad y separa los
datos mediante schemas en la misma base:

- `public`: aplicación transaccional OLTP;
- `analytics`: dimensiones, hechos, puente y tablas de control ETL.

Esta decisión responde al presupuesto y a las restricciones de AWS Academy.
No ofrece aislamiento físico de cómputo: si la carga analítica creciera o
afectara al OLTP, el contrato dimensional debe migrarse a una segunda RDS o a
un warehouse administrado. También deja explícita la desviación frente a una
lectura literal del requerimiento de una segunda base PostgreSQL: en esta
versión prevalece el requerimiento acordado de un schema `analytics` en RDS.

## 2. Diagramas

| Vista | Qué responde | Archivo |
|---|---|---|
| Flujo ETL | ¿Qué ocurre en cada ejecución y cómo falla de forma segura? | [Draw.io](../diagramas/flujo-etl.drawio) · [PNG](../diagramas/flujo-etl.drawio.png) |
| Flujo de datos | ¿Qué fuentes alimentan cada grupo analítico? | [Draw.io](../diagramas/flujo-datos-analitica.drawio) · [PNG](../diagramas/flujo-datos-analitica.drawio.png) |
| Arquitectura AWS | ¿Dónde se ejecutan la aplicación y el ETL y cómo se conectan? | [Draw.io](../diagramas/arquitectura-aws.drawio) · [PNG](../diagramas/arquitectura-aws.drawio.png) |
| ERD OLTP | ¿Cuál es el modelo transaccional de origen? | [Draw.io](../diagramas/airline-oltp-erd.drawio) · [PNG](../diagramas/airline-oltp-erd.drawio.png) |

## 3. Arquitectura lógica y física

La aplicación FastAPI se ejecuta en EC2 y accede al schema `public` de una RDS
PostgreSQL privada. La capa analítica agrega un job AWS Glue 4.0, dos conexiones
JDBC con TLS, dos bases lógicas en Glue Data Catalog, dos crawlers bajo demanda,
un bucket S3 privado para el script y temporales, métricas/logs en CloudWatch y
un trigger Glue horario.

El job no contiene una segunda implementación de las reglas. Resuelve el
endpoint con las conexiones Glue y, por JDBC, invoca la función versionada
`analytics.refresh_warehouse(run_id, snapshot_at)`. La transformación
set-based vive en PostgreSQL y es gestionada por Alembic; así, el runner local
y AWS Glue usan el mismo contrato.

El tráfico Glue–RDS circula por ENI en subred privada y un security group
dedicado. RDS solo admite PostgreSQL desde los grupos de la API y de Glue. El
acceso privado de Glue a S3 utiliza un Gateway VPC Endpoint, evitando un NAT
Gateway permanente.

## 4. Fuentes OLTP autorizadas

El crawler y el diseño limitan la extracción a doce tablas necesarias:

| Dominio | Tablas `public` | Uso |
|---|---|---|
| Reservas | `reservations`, `reservation_items` | Grano reserva y pasajero-tramo, fechas, importes y estados |
| Dinero | `payments`, `refunds` | Ingreso aprobado, reembolsos e ingreso neto |
| Operación | `inventories`, `flight_leg_instances`, `flight_instances` | Capacidad, ocupación, salida y vuelo operacional |
| Programación | `scheduled_flights`, `scheduled_legs` | Número de vuelo, secuencia, origen y destino |
| Catálogos | `cabins`, `agencies` | Cabina y canal de agencia |
| Auditoría | `audit_events` | Cancelación y confirmación previas, sin copiar actores |

No se cargan nombres, apellidos, documentos, localizadores, actores, agentes,
credenciales ni claves de idempotencia. Los identificadores técnicos de fuente
se conservan únicamente para lineage, actualización e idempotencia.

## 5. Modelo dimensional

### 5.1 Dimensiones

| Tabla | Clave natural o de fuente | Propósito |
|---|---|---|
| `dim_date` | `date_key` (`YYYYMMDD`) | Fechas role-playing de creación, salida y cancelación |
| `dim_route` | `source_route_id` | Tramo programado, origen, destino y código trazable |
| `dim_flight` | `source_flight_instance_id` | Instancia operacional, número, fecha y estado |
| `dim_cabin` | `cabin_code` | Cabina comercial |
| `dim_fare_band` | `fare_band_code` | Anticipación `0–6`, `7–30` y `31+` días |
| `dim_channel` | `channel_code` | Canal de venta |
| `dim_agency` | `source_agency_id` | Agencia sin información de agentes individuales |

Las dimensiones se actualizan con `UPSERT`. El diseño implementa estado actual
(equivalente a SCD tipo 1); no promete historial de atributos dimensionales.

### 5.2 Hechos y puente

| Tabla | Grano | Medidas principales | Idempotencia |
|---|---|---|---|
| `fact_sales_segment` | Un `reservation_item`: un pasajero y un tramo operacional | tarifa, tasa, impuesto, bruto, ingreso aprobado, refund, neto, comisión | `source_reservation_item_id` único |
| `fact_reservation` | Una reserva | total, comisión, anticipación, flags de cancelación y confirmación previa | `source_reservation_id` único |
| `fact_leg_occupancy` | Un inventario de tramo/cabina por snapshot ETL | capacidad, retenidos, confirmados, disponibles y ratio | `(source_inventory_id, snapshot_at)` único |
| `bridge_reservation_route` | Una relación reserva–ruta | secuencia y fecha de salida | PK reserva–ruta y secuencia única por reserva |

El puente permite filtrar reservas multi-tramo sin multiplicar el conteo de la
reserva. Las fechas tienen roles explícitos; no existe una fecha genérica con
semántica cambiante. Los valores monetarios usan `numeric(14,2)` y COP por
defecto.

## 6. Ejecución del ETL

El trigger `airline-analytics-etl-hourly` usa la expresión Glue
`cron(0 * * * ? *)`. Se ejecuta al minuto `00` de cada hora, en UTC. En hora de
Colombia (UTC−5, sin cambio estacional), también ocurre al minuto `00` de cada
hora local. `StartOnCreation` permanece en `false`: el script de despliegue lo
activa únicamente después de cargar el job en S3.

Cada corrida sigue esta secuencia:

1. Glue crea un `run_id` UUID y un `snapshot_at` UTC.
2. Abre la conexión JDBC y una transacción `REPEATABLE READ`.
3. La función toma un advisory lock transaccional. Glue también limita
   `MaxConcurrentRuns` a `1`, por lo que no se publican dos cargas simultáneas.
4. Registra `RUNNING` y carga primero las siete dimensiones.
5. Construye el conjunto de ventas, asigna pagos aprobados y refunds a los
   ítems proporcionalmente a su importe bruto, y aplica el residuo de redondeo
   al último ítem para conservar igualdad exacta.
6. Hace `UPSERT` de reservas, puente y ventas, y agrega el snapshot de ocupación.
7. Compara conteos de reservas, ítems e inventarios, además de sumas de ingreso
   aprobado y refunds, entre fuente y destino.
8. Si todas las diferencias son cero, marca `SUCCEEDED`, publica conteos y
   reconciliación, actualiza `etl_watermark` y confirma la transacción.
9. Si algo falla, PostgreSQL revierte toda la carga. El caller registra `FAILED`
   en una transacción separada con un mensaje sanitizado; el watermark no avanza.

La extracción actual es un snapshot completo intencional. No se usan bookmarks
basados solo en `created_at`, porque pagos, refunds, estados y eventos pueden
modificar una reserva después de su creación.

## 7. Idempotencia, consistencia y datos tardíos

- Repetir un `run_id` ya exitoso con el mismo `snapshot_at` es un no-op.
- Reutilizar el mismo `run_id` con otro snapshot es un error explícito.
- Las claves únicas de fuente evitan duplicar reservas y ventas.
- Un mismo snapshot de ocupación puede reintentarse sin crear otra fila.
- Un snapshot nuevo conserva el historial de ocupación.
- El snapshot completo y los `UPSERT` reflejan pagos, refunds, cancelaciones y
  cambios operacionales que llegaron después de una corrida previa.
- `REPEATABLE READ` fija la visión de fuente durante la transacción; publicación
  y controles se confirman como una unidad.

## 8. Calidad y observabilidad

Una corrida solo es exitosa si cumple simultáneamente:

- reservas fuente = filas correspondientes en `fact_reservation`;
- ítems fuente = filas correspondientes en `fact_sales_segment`;
- inventarios fuente = filas del snapshot actual en `fact_leg_occupancy`;
- pagos `APPROVED` = suma de `approved_revenue`;
- refunds = suma de `refund_amount`;
- `approved_delta = 0.00` y `refund_delta = 0.00`.

`analytics.etl_run` conserva inicio, fin, cutoff, estado, conteos,
reconciliación JSON y error. `analytics.etl_watermark` solo conserva la última
corrida exitosa. Glue publica métricas, job insights y logs continuos en
CloudWatch. Las consultas operativas y comandos de verificación están en el
[runbook de despliegue](deployment/analytics-runbook.md).

## 9. Seguridad y gobierno

- RDS permanece en subredes privadas y JDBC exige `sslmode=require` y
  `JDBC_ENFORCE_SSL=true`.
- El bucket de artefactos bloquea acceso público, usa SSE-S3 y versionado.
- El endpoint Gateway mantiene el tráfico S3 dentro de la red de AWS.
- Los crawlers catalogan una lista permitida de fuentes y el schema analítico;
  no hacen un barrido indiscriminado de `public`.
- La función es `SECURITY INVOKER`: no eleva permisos del rol que la llama.
- AWS Academy obliga a reutilizar `LabRole`; es una excepción del laboratorio.
  Producción debe utilizar roles dedicados de mínimo privilegio, credenciales
  en Secrets Manager y roles PostgreSQL separados para migración, aplicación y
  ETL.

## 10. Despliegue y operación

Orden requerido:

1. Validar la plantilla y configurar el ARN real de `LabRole` sin guardar
   secretos en Git.
2. Desplegar o actualizar CloudFormation con
   `deploy/update-analytics-stack.sh`.
3. Ejecutar el bootstrap de la aplicación para aplicar Alembic hasta
   `0007_analytics_refresh`; los crawlers no crean el schema.
4. Subir `analytics/glue_job.py` al bucket. El script de actualización hace
   esta operación con SSE-S3.
5. Ejecutar los crawlers cuando cambie el schema y comprobar ambos catálogos.
6. Activar el trigger y verificar una corrida `SUCCEEDED`, diferencias cero y
   repetición idempotente.

Para detener el costo horario sin eliminar recursos:

```bash
aws glue stop-trigger --name airline-analytics-etl-hourly \
  --profile academy-lab --region us-east-1
```

Para reanudarlo, usar `start-trigger`. Los crawlers permanecen bajo demanda;
no es necesario ejecutarlos cada hora porque catalogan estructura, no cargan
los hechos.

## 11. Capacidad, costo y evolución

El job usa Glue 4.0 con dos workers `G.1X`, timeout de 30 minutos y una corrida
concurrente. Al ejecutarse cada hora, el costo depende de la duración real;
debe detenerse fuera de las ventanas del laboratorio cuando no se necesite.
El desglose estimado está en [arquitectura analítica](analytics-architecture.md).

El snapshot completo es adecuado para el volumen académico. Antes de crecer
aproximadamente 10× se deben medir duración, CPU/IO de RDS y desfase del
watermark. La evolución prevista es captura incremental confiable hacia
staging, `MERGE` al modelo dimensional y aislamiento físico del destino. Ese
cambio no debe alterar el grano ni las claves de negocio ya publicadas.

## 12. Estado de verificación

La migración, el contrato dimensional, el ETL local, la reconciliación y el
scheduler cuentan con pruebas reproducibles. La evidencia disponible está en
[validación analítica](evidence/analytics-validation.md). Esa evidencia no
afirma ejecución remota: la sesión de AWS Academy usada durante el desarrollo
denegó operaciones de CloudFormation y Glue. Por tanto, los artefactos están
preparados y validados localmente, pero la activación y primera corrida horaria
deben confirmarse con una sesión Learner Lab vigente.

## 13. Fuentes de verdad del repositorio

| Contrato | Archivo |
|---|---|
| DDL dimensional | `backend/alembic/versions/0006_analytics_schema.py` |
| Transformación y reconciliación | `backend/alembic/versions/0007_analytics_refresh.py` |
| Runner local | `analytics/etl.py` |
| Entrypoint Glue | `analytics/glue_job.py` |
| Recursos AWS y cron | `infra/airline-learner-lab.yaml` |
| Operación | `docs/deployment/analytics-runbook.md` |

Los diagramas comunican el diseño, pero estos artefactos versionados son la
autoridad ejecutable.
