# ADR-0003: Política operativa, idempotencia autoritativa y acceso demo

Status: accepted (MVP)

## Contexto

El esquema ya incluía `fare_rules` y `operational_settings`, pero varias reglas se
aplicaban como constantes del código. Además, la reserva conservaba columnas de
idempotencia a la vez que existía `idempotency_records`. La API de demostración
necesita separar pasajeros, agencias, administración y aeropuerto sin presentar
encabezados controlados por el cliente como autenticación productiva.

## Decisión

`BookingService` carga en cada transacción una instantánea de política desde
`fare_rules` y `operational_settings`. Esa política gobierna la retención, vigencia
de cotización, ventana y corte de venta, corte de cancelación, porcentaje de
reembolso, multiplicadores, impuesto y comisión. Los valores sembrados son los
defaults reproducibles; una actualización administrativa afecta operaciones
posteriores, mientras cada `ReservationItem` conserva el precio aplicado.

`idempotency_records` es la autoridad durante la ventana de 24 horas. Una llave se
serializa con un advisory lock transaccional de PostgreSQL, se asocia al hash
canónico del payload y al recurso creado, y un reintento idéntico recupera ese
recurso. Un payload diferente produce `IDEMPOTENCY_KEY_REUSED`. Las columnas
históricas de `reservations` se conservan como evidencia de la solicitud y por
compatibilidad migratoria, pero no deciden el replay. La referencia de operación
única cumple la misma función para pagos.

Las identidades de la demostración están registradas y activas en
`demo_identities`. La API contrasta identidad, rol y, para agentes, agencia contra
la base de datos; no confía solo en `X-Demo-*`. Esta es una frontera deliberadamente
limitada a la demo y no equivale a autenticación, autorización o gestión de
sesiones de producción.

Las migraciones `0004` y `0005` añaden integridad referencial para atribución de
agencia y el catálogo de identidades demo. Alembic sigue siendo la única autoridad
DDL del despliegue; `create_all()` queda restringido a fixtures de prueba.

## Consecuencias

Cambiar una regla no reescribe reservas existentes ni sus importes. La
idempotencia no depende de la fecha de creación de la reserva y permite reutilizar
la llave después de expirar su registro. Los encabezados demo son adecuados para
una exposición temporal y controlada del curso, pero el servicio no debe publicarse
como sistema real ni manejar datos sensibles hasta sustituirlos por autenticación
productiva y autorización de recursos.
