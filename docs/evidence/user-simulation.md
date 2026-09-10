# Simulación de usuarios concurrentes

Fecha: 2026-09-10

Destino: `http://44.198.192.232:8000`

## Capacidad desplegada

El avión demo fue ampliado mediante un seed idempotente y sin eliminar registros históricos:

- Economy: 150 asientos y capacidad 150 por tramo;
- Business: 12 asientos y capacidad 12 por tramo;
- tres tramos operativos actualizados;
- 162 pasajeros totales por vuelo.

La verificación directa posterior confirmó exactamente 150 filas de asiento Economy y 12 Business.

## Validación pequeña

Se ejecutaron 6 usuarios con concurrencia 3 y sin retener inventario:

- 6 reservas creadas;
- 45 solicitudes HTTP;
- 3 confirmaciones canceladas con reembolso;
- 2 pagos rechazados;
- 1 hold cancelado;
- cero errores y cero conflictos de inventario.

## Carga inicial

Comando equivalente:

```bash
./deploy/simulate-users.sh \
  --base-url http://44.198.192.232:8000 \
  --users 100 \
  --concurrency 8 \
  --seed 20260910 \
  --quiet
```

Resultado:

- duración: 18.58 segundos;
- rendimiento: 5.38 usuarios por segundo;
- solicitudes HTTP: 528, todas exitosas;
- reservas creadas: 92;
- búsquedas abandonadas: 8;
- holds cancelados: 20;
- pagos rechazados: 25;
- reservas confirmadas y conservadas: 3;
- reservas pendientes: 3;
- confirmaciones canceladas y reembolsadas: 41;
- replay idempotente de reserva: 10;
- replay idempotente de pago: 4;
- latencia p50: 210.48 ms;
- latencia p95: 284.70 ms;
- latencia máxima: 1201.63 ms;
- errores y conflictos de inventario: 0.

La ejecución dejó estados transaccionales variados sin guardar credenciales ni acceder directamente a PostgreSQL.

## Estado posterior

Incluyendo la validación funcional del despliegue y la corrida pequeña, la API administrativa reportó:

- 99 reservas persistidas;
- 66 canceladas;
- 27 con pago rechazado;
- 3 confirmadas;
- 3 pendientes de pago;
- disponibilidad mínima de 145 en Economy y 12 en Business;
- contenedor `running healthy`.

## Itinerario y simulación continua

El 10 de septiembre se desplegó el calendario diario del 11 al 20 de septiembre y se conservó el histórico de 99 reservas. La verificación directa posterior al seed confirmó:

- 2 aeronaves `DEMO-A320`, cada una con 150 sillas Economy y 12 Business;
- 40 instancias de vuelo y 50 instancias de tramo;
- 100 filas de inventario, una por tramo y cabina;
- cero solapamientos al ordenar los tramos de cada aeronave;
- API saludable después de reemplazar el contenedor.

Se dejó `airline-simulator` ejecutándose en la misma EC2 con reinicio `unless-stopped`, llegada de usuarios cada 10–25 segundos y pausas de 5–45 segundos entre acciones. El primer escaneo descubrió las 100 combinaciones tramo/cabina y calculó 2.433 sillas objetivo sobre 8.100 disponibles: 30,04% global, con metas individuales entre 24% y 36%.

En los primeros dos minutos el proceso registró búsquedas abandonadas y confirmaciones en Economy y Business. La base pasó de 99 a 106 reservas, 136 pasajeros y 10 plazas confirmadas, con una marca de auditoría real del momento de ejecución. Ambos contenedores permanecieron activos; en la muestra, la API consumía aproximadamente 63 MiB y el simulador 17 MiB.
