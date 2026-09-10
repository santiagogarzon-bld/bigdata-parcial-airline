# Evidencia de aceptación del MVP OLTP

Ejecución local del 9 de septiembre de 2026 (zona America/Bogota), con Python
3.12.3 y PostgreSQL 16.15 en el contenedor desechable de Docker Compose. No se
usó SQLite ni se creó recurso alguno en AWS.

## Base de datos, API y calidad

La instalación editable declarada se verificó con `python3 -m pip install -e
'.[dev]'`. El primer intento detectó ambigüedad de paquetes tras añadir
`backend/deploy`; se corrigió el discovery a `airline_core*` y la instalación
posterior construyó e instaló el paquete correctamente.

```text
$ python3 -m airline_core.persistence.bootstrap --with-demo-data
bootstrap complete: schema=head, parameters=upserted, demo=upserted
$ python3 -m airline_core.persistence.bootstrap --with-demo-data
bootstrap complete: schema=head, parameters=upserted, demo=upserted
$ python3 -m pytest -q
31 passed, 1 warning in 16.05s
$ python3 -m ruff check .
All checks passed!
$ python3 -m mypy airline_core
Success: no issues found in 15 source files
```

La advertencia restante proviene de la transición de `starlette.testclient`
desde `httpx` hacia `httpx2`; no es una advertencia de la aplicación. La suite
prueba migración desde vacío y upgrades conservando una reserva válida desde
`0001`, `0002` y `0003` hasta `0005`.

La corrida con cobertura de dominio y aplicación produjo:

```text
31 passed in 19.05s
Required test coverage of 90.0% reached. Total coverage: 90.50%
```

Las nueve pruebas HTTP cubren búsqueda directa/conexión con fecha local,
capacidad y precio máximo; respuesta anidada; lookup por apellido; idempotencia
de reserva/pago; atribución de agencia; roles persistidos; aprobación, tickets,
cupones, manifiesto, cancelación, reembolso y liberación; rechazo; expiración;
administración y política runtime; OpenAPI, estáticos, CSP y errores estables,
incluido un 500 sanitizado.

## Contención PostgreSQL

```text
$ AIRLINE_CONCURRENCY_ITERATIONS=30 python3 -m pytest -q -m concurrency
2 passed, 29 deselected in 46.93s
```

Son 30 iteraciones por cada escenario (directo y dos tramos), 20 sesiones
simultáneas por iteración: 1.200 solicitudes. Cada iteración afirma exactamente
una ganadora, 19 conflictos controlados, disponibilidad final cero, una sola
silla física y ninguna reserva parcial.

## Frontend, imagen y HTTP real

```text
$ node --check frontend/app.js
$ node --check frontend/client-logic.js
$ node frontend/test.js
frontend contract/DOM tests: 24 passed
$ docker build -t airline-api:demo .
Successfully tagged airline-api:demo
$ docker exec airline-api-verification python -m airline_core.persistence.bootstrap --with-demo-data
bootstrap complete: schema=head, parameters=upserted, demo=upserted
$ BASE_URL=http://127.0.0.1:18000 ./deploy/smoke-test.sh
smoke test passed: http://127.0.0.1:18000
```

La imagen se ejecutó como `uid=999(airline)`, quedó `running healthy` y sirvió
HTML, JavaScript, health y OpenAPI. Un cliente HTTP externo al proceso ejecutó:

```text
real HTTP E2E passed: search -> hold -> lookup -> pay -> tickets -> manifest -> cancel -> refund/VOID/inventory
```

Esta prueba detectó y permitió corregir una carrera del commit posterior al
`yield`: el middleware transaccional ahora hace `COMMIT` antes de devolver una
respuesta exitosa y `ROLLBACK` antes de devolver un error.

## Infraestructura y secretos

```text
$ bash -n deploy/*.sh infra/*.sh
$ ./infra/validate.sh
infrastructure validation passed
$ ./infra/validate-negative.sh
negative infrastructure checks passed
$ cfn-lint infra/airline-learner-lab.yaml
W1011 Use dynamic references over parameters for secrets
```

La única advertencia de `cfn-lint` 1.56.2 es intencional: Learner Lab recibe la
contraseña como parámetro `NoEcho` y por entrada runtime; no se crea Secrets
Manager ni IAM. El escaneo confirmó que la plantilla no contiene
`AWS::IAM::*`, NAT Gateway, Multi-AZ, Enhanced Monitoring, RDS pública ni 5432
global. Las únicas cadenas PostgreSQL con contraseña halladas son las
credenciales locales `airline_local_only` ya documentadas para Docker Compose;
no se hallaron llaves AWS, URLs firmadas, tokens ni claves privadas.

No se ejecutó `aws cloudformation create-stack` ni ninguna mutación AWS/IAM. El
warning W1011 debe reevaluarse al migrar fuera de las restricciones académicas.
