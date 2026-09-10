# Catálogo de diagramas

Todos los archivos editables de Draw.io del proyecto están centralizados en
esta carpeta. Las imágenes PNG son vistas previas generadas desde la misma
fuente y no deben editarse directamente.

| Diagrama | Propósito | Fuente editable | Vista previa |
|---|---|---|---|
| Flujo ETL | Secuencia operativa de una corrida, controles y ruta de error | [flujo-etl.drawio](flujo-etl.drawio) | [flujo-etl.drawio.png](flujo-etl.drawio.png) |
| Flujo de datos | Mapeo de fuentes OLTP, transformación y modelo dimensional | [flujo-datos-analitica.drawio](flujo-datos-analitica.drawio) | [flujo-datos-analitica.drawio.png](flujo-datos-analitica.drawio.png) |
| Arquitectura AWS | Vista integral de la aplicación transaccional y la capa analítica | [arquitectura-aws.drawio](arquitectura-aws.drawio) | [arquitectura-aws.drawio.png](arquitectura-aws.drawio.png) |
| ERD OLTP | Modelo relacional que actúa como fuente del ETL | [airline-oltp-erd.drawio](airline-oltp-erd.drawio) | [airline-oltp-erd.drawio.png](airline-oltp-erd.drawio.png) |

## Convenciones visuales

- Azul: flujo de datos o tráfico de aplicación.
- Morado discontinuo: programación, invocación o dependencia administrada.
- Rosa discontinuo: control, metadatos o ruta de error.
- Verde: datos analíticos publicados correctamente.
- Los cilindros RDS separados representan instancias físicas distintas; los
  marcos grises restantes representan límites lógicos o de servicio.

La documentación de ingeniería de datos que explica decisiones, grano,
operación y controles está en
[Diseño detallado de la capa analítica](../docs/analytics-detailed-design.md).
