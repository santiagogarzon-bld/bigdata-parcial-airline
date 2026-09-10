# Simulación de usuarios concurrentes

El simulador `deploy/simulate-users.sh` genera actividad transaccional usando exclusivamente la API HTTP. No se conecta directamente a PostgreSQL ni inserta filas fuera de las reglas de negocio de la aplicación.

## Itinerario operacional del 11 al 20 de septiembre de 2026

El seed crea la misma rotación cada día, en hora local de Colombia (`America/Bogota`). Hay cuatro vuelos comerciales y cinco tramos diarios, porque `DE200` tiene escala en Medellín:

| Avión | Vuelo | Tramo | Sale | Llega | Giro antes del siguiente tramo |
|---|---|---|---:|---:|---:|
| `DEMO-A320-01` | `DE100` | BOG → MDE | 07:00 | 08:00 | 75 min |
| `DEMO-A320-01` | `DE101` | MDE → BOG | 09:15 | 10:15 | fin de rotación |
| `DEMO-A320-02` | `DE200` | BOG → MDE | 08:00 | 09:00 | 60 min |
| `DEMO-A320-02` | `DE200` | MDE → CLO | 10:00 | 11:00 | 75 min |
| `DEMO-A320-02` | `DE201` | CLO → BOG | 12:15 | 13:25 | fin de rotación |

En total son 40 instancias de vuelo y 50 instancias de tramo durante los diez días. Cada avión tiene 150 sillas Economy y 12 Business. El mismo identificador físico de avión nunca aparece en dos tramos que se solapen; la prueba de bootstrap ordena todos sus tramos y comprueba que cada salida sea posterior o igual a la llegada anterior.

## Simulación continua a ritmo humano

`airline_core.traffic_daemon` es el controlador de larga duración. En lugar de completar miles de operaciones en un bucle inmediato:

- inicia un usuario nuevo cada 10 a 25 segundos;
- cada usuario espera entre 5 y 45 segundos entre buscar, reservar, consultar, pagar, consultar tickets o cancelar;
- admite hasta ocho recorridos intercalados, como ocurriría con visitantes independientes;
- genera nombres sintéticos, canal directo o agencia, uno o dos pasajeros y llaves idempotentes propias;
- escribe cada operación mediante la API, por lo que `created_at`, pagos, auditoría, tickets, reembolsos y demás marcas de tiempo corresponden al instante real de ejecución.

Cada cinco minutos vuelve a leer búsqueda e inventario. La meta no es idéntica para todos los vuelos: aplica de forma determinista 24%, 27%, 30%, 33% o 36% por tramo y cabina, con promedio de flota cercano al 30%. Escoge con más frecuencia los mayores faltantes y da prioridad adicional a las salidas próximas. Al alcanzar las metas deja de conservar nuevas confirmaciones, pero sigue produciendo búsquedas, holds cancelados, pagos rechazados y cancelaciones confirmadas válidas, de modo que la historia transaccional continúa creciendo sin llenar indefinidamente la cabina.

La mezcla mientras falta ocupación es aproximadamente:

| Recorrido | Proporción | Efecto neto en ocupación |
|---|---:|---|
| Confirmación conservada | 60% | aumenta confirmados |
| Confirmación y cancelación | 10% | libera la silla y conserva la historia completa |
| Pago rechazado | 15% | libera la silla |
| Cancelación del hold | 10% | libera la silla |
| Solo búsqueda | 5% | no altera inventario |

Para salidas a menos de 24 horas, el 10% de confirmación y cancelación se redistribuye entre cancelación de hold y pago rechazado. Así, el simulador respeta la política real de cancelación en vez de forzar una operación inválida.

El contenedor se inicia en la EC2 con:

```bash
EC2_HOST=44.198.192.232 ./deploy/start-continuous-simulation.sh
```

Usa la misma imagen que la API, red local de la instancia y `--restart unless-stopped`, por lo que vuelve a arrancar después de reiniciar Docker o la EC2. Operación básica:

```bash
ssh -i ~/.ssh/airline-demo-key ec2-user@44.198.192.232 \
  'docker ps --filter name=airline-simulator'
ssh -i ~/.ssh/airline-demo-key ec2-user@44.198.192.232 \
  'docker logs --tail 100 airline-simulator'
ssh -i ~/.ssh/airline-demo-key ec2-user@44.198.192.232 \
  'docker stop airline-simulator'
ssh -i ~/.ssh/airline-demo-key ec2-user@44.198.192.232 \
  'docker start airline-simulator'
```

Los logs JSON incluyen `inventory_scan`, avance global hacia la meta, `user_complete`, escenario y resultado. El controlador no altera horarios ni despega vuelos: solo simula comportamiento comercial sobre el itinerario ya sembrado.

## Ejecución

```bash
./deploy/simulate-users.sh \
  --base-url http://44.198.192.232:8000 \
  --users 100 \
  --concurrency 8
```

Cada usuario se ejecuta en un hilo independiente. Un evento compartido libera simultáneamente los primeros hilos hasta el límite indicado por `--concurrency`. Las operaciones de un mismo usuario son secuenciales, pero las secuencias de usuarios diferentes se intercalan:

```text
usuario A: buscar → reservar → consultar → pagar → tickets → cancelar
usuario B:     buscar → reservar → cancelar hold
usuario C: buscar → reservar → pago rechazado
```

La fecha se descubre buscando disponibilidad BOG-MDE dentro de los próximos 30 días. Después, cada usuario elige BOG-MDE o BOG-CLO y puede usar Economy o Business, canal directo o agencia y uno o dos pasajeros.

## Distribución predeterminada

| Recorrido | Porcentaje | Resultado persistido |
|---|---:|---|
| Solo búsqueda | 10% | El usuario abandona sin reservar |
| Reserva pendiente | 5% | Hold activo hasta pago, cancelación o expiración |
| Cancelación de hold | 20% | Reserva cancelada y asientos liberados |
| Pago rechazado | 25% | Pago rechazado, reserva fallida y asientos liberados |
| Confirmación conservada | 5% | Pago aprobado, tickets y cupones emitidos |
| Confirmación cancelada | 35% | Pago, tickets, cancelación, reembolso y liberación |

Además:

- 20% usa el agente sintético de la agencia;
- 20% solicita Business;
- 20% solicita dos pasajeros;
- 10% repite la reserva o el pago con la misma llave idempotente;
- hay pausas aleatorias de hasta 250 ms entre acciones;
- una reserva con contención puede reintentar hasta cinco veces.

La configuración conserva pocas reservas porque el A320 demo tiene 150 plazas Economy y 12 Business. Las cancelaciones y pagos rechazados permiten generar historia transaccional sin agotar rápidamente los vuelos.

## Condiciones de carrera

El tráfico es realmente concurrente, aunque una ejecución normal no garantiza que ocurra una colisión. La carrera principal sucede sobre el inventario:

1. varios usuarios buscan el mismo vuelo;
2. todos pueden observar la misma disponibilidad;
3. intentan reservar simultáneamente;
4. PostgreSQL serializa el acceso a cada fila de inventario con `SELECT ... FOR UPDATE`;
5. cada transacción vuelve a comprobar la capacidad después de obtener el bloqueo;
6. si otro usuario consumió el último asiento, la operación recibe `409 INVENTORY_UNAVAILABLE`.

Los itinerarios con conexión bloquean las filas de inventario en un orden determinista. Esto evita que dos reservas de varios segmentos tomen los mismos bloqueos en orden contrario y reduce la posibilidad de deadlock.

Un índice único parcial, `uq_active_seat_assignment`, impide que dos elementos activos tengan el mismo asiento y tramo. Esta restricción actúa como última defensa aunque falle una validación de aplicación.

Por tanto, una búsqueda puede quedar obsoleta antes de la reserva —comportamiento normal en sistemas de venta—, pero la transacción de reserva no puede producir sobreventa.

## Idempotencia

La creación usa `Idempotency-Key` y los pagos usan una `operation_reference` única. El simulador puede repetir cualquiera de las dos solicitudes:

- el mismo payload devuelve la operación original;
- un payload distinto con la misma llave es rechazado;
- no se duplican reservas, pagos ni consumo de inventario.

Los replays del simulador general son secuenciales dentro de un usuario. Validan la semántica idempotente, pero no envían dos copias exactamente en el mismo instante.

## Perfil adversarial de inventario

Este comando dirige 100 usuarios hacia los 12 asientos Business, sin pausas y reteniendo el inventario:

```bash
./deploy/simulate-users.sh \
  --base-url http://44.198.192.232:8000 \
  --users 100 \
  --concurrency 50 \
  --business-percent 100 \
  --two-passenger-percent 100 \
  --search-only-percent 0 \
  --pending-percent 50 \
  --cancel-hold-percent 0 \
  --decline-percent 0 \
  --confirmed-percent 50 \
  --max-pause 0
```

Como cada reserva solicita dos plazas, solo unas seis pueden retener Business por tramo. El resto debe obtener una búsqueda sin disponibilidad, reintentar otro itinerario o recibir un conflicto de inventario. En ningún caso la suma `held + confirmed` debe superar 12.

Este perfil modifica el estado del vuelo desplegado y puede dejar Business lleno. Debe usarse deliberadamente, o contra el PostgreSQL local, cuando se quiera demostrar contención.

## Cobertura y límites

La simulación general cubre concurrencia entre usuarios independientes:

- búsquedas simultáneas;
- reservas sobre inventario compartido;
- rutas directas y con conexión;
- pagos aprobados y rechazados;
- holds, confirmaciones y cancelaciones;
- emisión y anulación de tickets y cupones;
- reembolsos;
- consultas de reserva y manifiesto;
- replays idempotentes.

Todavía no enfrenta dos acciones simultáneas sobre la misma reserva:

- pago contra cancelación;
- dos pagos con referencias distintas;
- dos cancelaciones;
- expiración del hold contra pago;
- dos copias idempotentes liberadas por la misma barrera.

Estas carreras requieren un modo adversarial que comparta una reserva entre varios workers. La suite `backend/tests/integration/test_concurrency.py` sí contiene una prueba de contención exacta con barrera para el último asiento, tanto en vuelo directo como en itinerario de dos segmentos. El perfil validado ejecuta 30 iteraciones por caso y 20 solicitudes simultáneas: 1.200 intentos en total. Comprueba un único ganador, ausencia de sobreventa, ausencia de asiento duplicado y ausencia de reservas parciales.

## Resultados y códigos de salida

El progreso individual se imprime en `stderr`; el resumen JSON se imprime en `stdout`. Esto permite guardar ambos por separado:

```bash
./deploy/simulate-users.sh \
  --base-url http://44.198.192.232:8000 \
  --users 500 \
  --concurrency 10 \
  2>simulation-progress.log \
  | tee simulation-summary.json
```

El resumen contiene:

- reservas creadas;
- recorridos y resultados;
- mezcla por canal, cabina, destino y tamaño del grupo;
- solicitudes por acción y código HTTP;
- conflictos de inventario;
- latencias p50, p95 y máxima;
- usuarios procesados por segundo.

Los códigos de salida son:

- `0`: todos los usuarios terminaron sin error fatal;
- `1`: al menos un usuario tuvo un error inesperado;
- `2`: falló la configuración, el healthcheck o el descubrimiento del vuelo.

Para una EC2 `t3.micro`, se recomienda empezar con concurrencia entre 5 y 10. Usa `./deploy/simulate-users.sh --help` para consultar todos los parámetros.
