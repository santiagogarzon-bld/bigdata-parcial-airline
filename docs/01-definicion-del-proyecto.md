# Definición del proyecto: sistema de reservas de aerolínea

Este documento es la entrada para la planeación técnica. Su propósito es hacer explícitas las decisiones que el enunciado dejó abiertas, registrar las restricciones de AWS Academy Learner Lab y evitar que un supuesto oculto se convierta en una decisión de arquitectura accidental.

No contiene todavía la arquitectura definitiva. Esa se elaborará después de responder este cuestionario y se trazará contra las respuestas, los requisitos y los seis pilares de AWS Well-Architected.

## Cómo completar este documento

1. Reemplazar cada `[POR RESPONDER]` después de **Respuesta**. Se puede escoger una opción sugerida o escribir una respuesta propia.
2. No escribir contraseñas, claves, tokens, ARN con datos sensibles ni credenciales temporales de AWS.
3. Si una decisión corresponde al profesor, escribir `POR CONFIRMAR CON EL PROFESOR`, junto con la fecha prevista para confirmarla.
4. Responder primero las preguntas marcadas **P0**. Sin ellas no es seguro cerrar la arquitectura ni estimar el costo.
5. Mantener los identificadores `Q-xxx`; se usarán para la trazabilidad de la planeación, los requisitos y las decisiones de arquitectura.

Estado de esta fase: **esperando respuestas del equipo**.

## 1. Condiciones confirmadas

### 1.1 Alcance obligatorio del parcial

Según el enunciado disponible en el repositorio, el proyecto debe producir como mínimo lo siguiente:[^1]

| ID | Entregable o condición obligatoria |
|---|---|
| OBL-01 | Requisitos funcionales en tabla: ID, descripción, actor y prioridad. |
| OBL-02 | Al menos un requisito no funcional medible para rendimiento, consistencia/concurrencia, disponibilidad, seguridad, escalabilidad y auditabilidad. |
| OBL-03 | Modelo ER en notación Chen o Crow's Foot y diccionario de datos por entidad. |
| OBL-04 | Resolver explícitamente itinerarios con escalas, vuelos recurrentes, asignación de silla e inventario que impida sobreventa. |
| OBL-05 | Diseño de arquitectura backend y frontend, justificado por FR/NFR. |
| OBL-06 | Backend parcial funcional con FastAPI y una base de datos que implemente el modelo. |
| OBL-07 | API mínima: buscar vuelos disponibles, crear una reserva y consultar una reserva. |
| OBL-08 | La creación de reservas debe implementar una estrategia real de concurrencia. |
| OBL-09 | Prueba concreta de dos solicitudes simultáneas por la última silla, con evidencia de que no hay sobreventa. |
| OBL-10 | Base transaccional y una segunda base PostgreSQL analítica (OLAP). |
| OBL-11 | ETL real que copie o transforme al menos una tabla o vista desde OLTP hacia OLAP. |
| OBL-12 | Ambas bases y sus tablas visibles como metadatos en AWS Glue Data Catalog. |
| OBL-13 | Diagrama AWS actualizado con bases, ETL y Glue Data Catalog. |
| OBL-14 | Tabla de justificación por servicio: alternativa, FR/NFR y pilar(es) Well-Architected. |
| OBL-15 | Proyección mensual de costos y escenario con 10 veces el volumen o la frecuencia. |
| OBL-16 | Guía de ejecución, código en GitHub y evidencia de pruebas. |
| OBL-17 | Declarar y justificar cualquier desviación entre diseño e implementación. |
| OBL-18 | Apéndice con los principales prompts y cómo fueron refinados o corregidos. |

La entrega parcial contiene FR y NFR; la entrega final integra todo lo anterior. La defensa oral puede invalidar una sección si el equipo no puede justificar sus decisiones.[^1]

### 1.2 Restricciones confirmadas de AWS Academy Learner Lab

La documentación de Learner Lab suministrada al equipo indica lo siguiente. Fue actualizada el **24 de junio de 2025**, advierte que las restricciones pueden cambiar y, por tanto, deberá validarse contra la cuenta real antes de desplegar:[^2]

| ID | Restricción o comportamiento | Consecuencia para el proyecto |
|---|---|---|
| ACA-01 | Acceso regional limitado a `us-east-1` y `us-west-2`. | Todos los recursos deben estar en una sola región permitida; la propuesta inicial es `us-east-1`. |
| ACA-02 | IAM tiene acceso extremadamente limitado. No se pueden crear usuarios ni grupos; la creación de roles es limitada. | Por decisión del proyecto, queda **prohibido crear, editar o eliminar IAM**. |
| ACA-03 | Existen `LabRole` y `LabInstanceProfile` precreados. Glue, EC2, Lambda y varios servicios pueden asumir `LabRole`. | Se reutilizarán únicamente esos recursos cuando sean suficientes; no se diseñarán roles personalizados. |
| ACA-04 | Glue admite solo workers `G.1X` o `Standard`, máximo 10 workers y concurrencia máxima 1. | El ETL debe ser pequeño, secuencial y probado con la capacidad mínima disponible. |
| ACA-05 | RDS permite PostgreSQL, clases nano/micro/small/medium, On-Demand, `gp2` hasta 100 GB y sin Enhanced Monitoring. | Single-AZ, clase burstable pequeña y almacenamiento mínimo son los candidatos iniciales. |
| ACA-06 | EC2 permite nano a large, solo On-Demand; máximo 9 instancias simultáneas y 32 vCPU por región. Intentar 20 o más puede desactivar la cuenta. | No se usarán clústeres ni escalado innecesario; el inventario de recursos debe revisarse antes de cada despliegue. |
| ACA-07 | El entorno es persistente, pero las instancias EC2 pueden detenerse al acabar la sesión y reiniciarse al iniciar otra. Su IP pública puede cambiar. | No se puede prometer disponibilidad continua en el laboratorio; se debe usar DNS/endpoint y separar NFR objetivo de limitación de demo. |
| ACA-08 | RDS puede no detenerse al terminar la sesión. | Requiere una rutina explícita de apagado o eliminación. |
| ACA-09 | El presupuesto visible se actualiza típicamente cada 8–12 horas. Superar el límite puede desactivar la cuenta y borrar el trabajo. | No se puede usar el saldo mostrado como control en tiempo real; se necesita presupuesto interno conservador. |
| ACA-10 | `Reset` elimina permanentemente los recursos y datos, pero no restablece el presupuesto. | No usar `Reset` como mecanismo cotidiano de limpieza. |
| ACA-11 | Los límites o usos indebidos de servicios pueden causar desactivación y eliminación de recursos. | Toda infraestructura debe probarse primero con un despliegue mínimo y una lista de recursos esperados. |

### 1.3 Regla IAM de este proyecto

Esta es una restricción no negociable solicitada por el equipo:

> No se creará, modificará ni eliminará ningún usuario, grupo, rol, política, perfil de instancia o recurso IAM. Tampoco se incluirán recursos `AWS::IAM::*` ni operaciones IAM en scripts o plantillas de infraestructura.

AWS Glue normalmente necesita que se le pase un rol con permisos sobre sus fuentes, destinos, scripts, S3 y recursos de red. La guía general de AWS suele instruir crear un rol, pero en Learner Lab el camino viable es seleccionar el `LabRole` preexistente, siempre que la cuenta permita `iam:PassRole` y el rol pueda ser asumido por Glue.[^3] La documentación particular de Learner Lab dice expresamente que Glue puede asumir `LabRole`.[^2] Esta capacidad debe comprobarse temprano; no debe suponerse.

Esta restricción impide aplicar plenamente mínimo privilegio. En la entrega se documentará como una excepción impuesta por el entorno educativo, no como una práctica recomendada para producción.

## 2. Preguntas P0: bloqueadores de la planeación

### Contexto académico y equipo

**Q-001 — P0. ¿Cuál es la restricción específica y confidencial asignada al equipo en la sección 3?** Debe copiarse literalmente, pues afecta requisitos, modelo y arquitectura.

> **Respuesta:** No hay, dejaron nuestro grupo sin restricción de negocio ni tecnica 

**Q-002 — P0. ¿Cuáles son las fechas y horas límite de la entrega parcial, entrega final y defensa oral?** 

> **Respuesta:** Dato operativo administrado fuera de este documento por solicitud del estudiante.

**Q-003 — P0. ¿Quiénes integran el equipo y qué disponibilidad semanal real tiene cada persona?**

> **Respuesta:** Santiago Garzon.

**Q-004 — P0. ¿Dónde se entregará el código?** Indicar URL del repositorio GitHub, rama de entrega y si será público o privado; no incluir credenciales.

> **Respuesta:** Repositorio Git local inicializado en la rama `main`. El remoto y su visibilidad se definirán antes de subirlo a GitHub.

**Q-005 — P0. ¿En qué idioma deben presentarse documento, diagramas, API y defensa?** Opciones: español; inglés; documento en inglés y trabajo interno en español.

> **Respuesta:** Ingles

**Q-006 — P0. ¿El profesor exige Amazon RDS o acepta PostgreSQL autogestionado en EC2/contenedores?** El enunciado exige PostgreSQL OLAP, pero no nombra explícitamente RDS como motor obligatorio. También confirmar si “cada database instance” significa dos instancias de cómputo separadas o dos bases lógicas.

> **Respuesta:** Diria que es importante usar RDS, por terminos didacticos

**Q-007 — P0. ¿El frontend debe implementarse o solo diseñarse?** El texto exige arquitectura frontend, mientras la primera implementación requerida es del backend.

> **Respuesta:** Implementarse de manera hiper simple

**Q-008 — P0. ¿Qué evidencia acepta el profesor?** Marcar: pruebas automatizadas; logs; capturas; video; demostración en vivo; exportación de Glue; otra.

> **Respuesta:** Tests automatizados

### Cuenta, tiempo y presupuesto

**Q-009 — P0. Confirmar el estado actual del presupuesto:** presupuesto total USD 50, consumido USD 5, saldo nominal USD 45. ¿Es correcto y de qué fecha/hora es la lectura?

> **Respuesta:** hoy de 5/50 USD.

**Q-010 — P0. ¿Cuándo expira o se cierra definitivamente el Learner Lab?** No confundir el temporizador de una sesión con la vigencia total del laboratorio.

> **Respuesta:** No se cierra en un tiempo, antes del parcial no es.

**Q-011 — P0. ¿Cuántas horas de ejecución real en AWS se esperan antes de la entrega?** Separar desarrollo, pruebas, ensayo y defensa.

> **Respuesta:** No se fija una cantidad ilimitada de horas. El límite operativo será el gasto adicional máximo de USD 15 definido en Q-012; las horas permitidas por recurso se calcularán con precios vigentes antes de desplegar. Los recursos se encenderán únicamente para pruebas, captura de evidencia, ensayo y defensa.

**Q-012 — P0. ¿Qué reserva de seguridad debe quedar sin consumir?** Recomendación inicial: reservar al menos USD 10 y tratar USD 35 como máximo adicional operativo.

> **Respuesta:** Se autoriza gastar como máximo USD 15 adicionales y se conservarán USD 30 de los USD 45 nominalmente disponibles como reserva de seguridad.

**Q-013 — P0. ¿Se autoriza destruir y recrear infraestructura entre sesiones, conservando datos/evidencias fuera de los recursos costosos?** Opciones: sí; solo después de snapshot/exportación; no.

> **Respuesta:** Si, despues de snapshots

**Q-014 — P0. ¿Existe ya algún recurso en la cuenta que consuma presupuesto?** Listar, por región, EC2, EBS, RDS/Aurora, snapshots, IP públicas/Elastic IP, NAT Gateway, Glue jobs/crawlers, S3 y otros. No incluir recursos preinstalados sin costo material.

> **Respuesta:** hay una EC2. No conozco el nombre.

### Alcance funcional esencial

**Q-015 — P0. ¿Qué actores estarán dentro del alcance?** Marcar y precisar: pasajero; agente de agencia; administrador; personal de aeropuerto; sistema de pagos; proceso ETL; analista comercial.

> **Respuesta:** Los actores serán: (1) pasajero/comprador, que busca vuelos, crea y consulta reservas, registra el resultado simulado del pago y cancela; (2) agente de agencia, que ejecuta el mismo flujo en nombre de pasajeros y deja atribuida la agencia; (3) administrador, que mantiene catálogos operativos y consulta reservas; (4) personal de aeropuerto, con consulta de solo lectura de vuelos, pasajeros y sillas confirmadas; (5) sistema de pagos simulado, que registra resultados sin procesar tarjetas; (6) proceso ETL, que extrae datos operativos y carga OLAP; y (7) analista comercial, que consulta ingresos por tarifa y cancelaciones. En el MVP, la función del personal de aeropuerto puede limitarse a un endpoint de consulta.

**Q-016 — P0. ¿Cuál será el alcance exacto del MVP implementado?** Recomendación mínima: búsqueda, creación de reserva y consulta, más carga de datos semilla y prueba concurrente. Indicar cualquier operación adicional que sí se implementará.

> **Respuesta:** Se interpreta “CRUD de tickets” como un flujo comercial, no como edición libre. La reserva retiene inventario; la compra ocurre cuando el pago simulado es aprobado; solo entonces se emite un ticket inmutable por pasajero, con un cupón por cada segmento. El MVP implementará: datos semilla; búsqueda de vuelos directos o con máximo una conexión; creación atómica de una reserva de uno o más pasajeros y todos sus segmentos; retención durante una hora; registro de pago simulado; emisión y consulta de tickets; consulta de reserva por localizador y apellido; cancelación total con anulación de tickets; expiración de reservas no pagadas; consulta administrativa/aeroportuaria; y prueba automatizada de concurrencia por la última unidad de inventario. Los catálogos de aeropuertos, aeronaves, rutas, vuelos programados, instancias y tarifas podrán tener CRUD administrativo básico. Una reserva confirmada o un ticket emitido nunca se actualizan o eliminan arbitrariamente: cambian solo mediante operaciones de dominio auditables.

**Q-017 — P0. ¿El pago será real, simulado o solo registrado como estado?** Si es simulado, definir resultados posibles: aprobado, rechazado, pendiente y reembolso simulado.

> **Respuesta:** El pago será simulado y se registrará en la base de datos. Los estados serán `PENDING`, `APPROVED`, `DECLINED` y `REFUNDED`. No se integrará una pasarela, no se recibirán PAN/CVV y cada intento tendrá una referencia sintética única para soportar idempotencia y auditoría.

**Q-018 — P0. ¿Cómo se representa un itinerario de varios trayectos?** Opción recomendada para evaluar: una reserva contiene un itinerario y este contiene segmentos ordenados, cada segmento asociado a una instancia concreta de vuelo.

> **Respuesta:** Una reserva contiene un único itinerario y este contiene segmentos ordenados. Cada segmento referencia una instancia concreta de tramo de vuelo (`FlightLegInstance`), no solo el vuelo completo. Así, un mismo número de vuelo puede hacer escalas y vender inventario por cada tramo operacional. La reserva es una sola transacción comercial: o se retiene inventario para todos los pasajeros en todos los segmentos, o no se crea ninguna retención.

**Q-019 — P0. ¿Se permite mantener sillas temporalmente antes de pagar?** Si sí, indicar duración, evento de expiración y qué ocurre si el pago llega tarde. Si no, explicar la atomicidad reserva/pago.

> **Respuesta:** Sí. Una reserva inicia en `PENDING_PAYMENT` y retiene inventario durante 60 minutos desde `created_at`, usando `expires_at`. Un pago aprobado antes del vencimiento confirma la reserva. Un pago recibido después del vencimiento se rechaza. Al vencer, la reserva pasa a `EXPIRED` y libera todo su inventario exactamente una vez. La corrección del inventario no dependerá exclusivamente de un proceso programado: las operaciones de disponibilidad y reserva ignorarán o procesarán retenciones vencidas dentro de su transacción.

**Q-020 — P0. ¿Cuál será la unidad de inventario que nunca puede quedar negativa?** Ejemplos: cupos por vuelo y cabina; sillas físicas por vuelo; cupos por tarifa; combinación de las anteriores.

> **Respuesta:** La unidad autoritativa será el cupo por `instancia de tramo de vuelo + cabina` (`FlightLegInstance + Cabin`). Para cada combinación se registran capacidad, unidades retenidas y unidades confirmadas; `available = capacity - held - confirmed` nunca puede ser negativo. La silla física se asigna adicionalmente por `instancia de tramo + seat`, con unicidad para impedir duplicados en tramos que se superponen. Esto permite vender la misma silla a pasajeros distintos en tramos consecutivos no superpuestos. Las tarifas no crean inventarios independientes en el MVP.

**Q-021 — P0. ¿Qué mecanismo de concurrencia quiere defender el equipo?** Opciones a evaluar: bloqueo pesimista de fila con transacción; control optimista con versión y reintentos; cola por vuelo; otro. Si no hay preferencia, escribir `RECOMENDAR DESPUÉS DEL ANÁLISIS`.

> **Respuesta:** Se adopta bloqueo pesimista en PostgreSQL mediante transacción y `SELECT ... FOR UPDATE` sobre cada fila de inventario requerida. En itinerarios de varios segmentos, las filas se bloquean en orden canónico por identificador de instancia de tramo y cabina para reducir deadlocks. Después de bloquear, se vuelve a comprobar disponibilidad, se crean todas las retenciones y se confirma la transacción; ante falta de cupo en cualquier segmento se hace rollback completo. Es apropiado para el MVP porque la fuente de verdad es una sola base PostgreSQL y la regla de no sobreventa tiene prioridad sobre maximizar throughput.

**Q-022 — P0. ¿Las cancelaciones y cambios se implementarán, solo se diseñarán o quedarán fuera del alcance?** Para cada uno, indicar reglas de negocio.

> **Respuesta propuesta:** La cancelación total sí se implementará porque se necesita analizar patrones de cancelación. Solo se permite para reservas `CONFIRMED` hasta 24 horas antes de la salida del primer segmento; libera inventario de todos los segmentos exactamente una vez y registra pago `REFUNDED` de manera simulada. También se permite cancelar una reserva `PENDING_PAYMENT`, sin reembolso. Cancelaciones parciales por pasajero o segmento y cambios de fecha/vuelo quedan fuera del MVP; se documentarán como extensión futura. Esta decisión privilegia consistencia y una implementación defendible.

### Datos y analítica

**Q-023 — P0. ¿Qué pregunta analítica será demostrada de extremo a extremo?** Elegir al menos una: ocupación por ruta; ingresos por tarifa; patrones de cancelación. Idealmente priorizar las tres y escoger una para el ETL mínimo.

> **Respuesta:** La capa de ingeniería deja preparadas las tres preguntas del escenario: ocupación reservada por ruta operacional y cabina, ingresos aprobados/netos por tarifa y cabina, y patrones de cancelación por ruta, fecha, canal y anticipación. Solo pagos `APPROVED` generan ingreso aprobado; los registros de `refunds` se asignan proporcionalmente por ítem y se restan para producir ingreso neto. `CANCELLED` identifica una cancelación voluntaria y `previously_confirmed` separa las cancelaciones con compra previa; `EXPIRED` y `PAYMENT_FAILED` nunca se cuentan como cancelaciones. Esta fase carga hechos confiables, pero no construye dashboards ni interpreta los indicadores.

**Q-024 — P0. ¿Qué frescura necesita OLAP?** Opciones: carga única para demostración; bajo demanda; diaria; cada hora; casi en tiempo real. Relacionar la respuesta con el presupuesto.

> **Respuesta:** Frescura objetivo de una hora. Un trigger programado de AWS Glue ejecuta el job al minuto 0 de cada hora (`cron(0 * * * ? *)`, en UTC). Para respetar el presupuesto del Learner Lab, se activa después de subir el artefacto y se desactiva cuando termina la ventana de demostración.

**Q-025 — P0. ¿El profesor permite que OLTP y OLAP compartan una instancia PostgreSQL como dos bases lógicas?** Aunque reduce costo, disminuye aislamiento y puede no satisfacer la intención de “cada instancia”.

> **Respuesta:** Se adoptan dos instancias Amazon RDS PostgreSQL privadas: `airline_oltp` para el modelo operacional y `airline_analytics` para el dimensional. Ambas usan la clase mínima `db.t3.micro`, 20 GB gp3 y Single-AZ. Solo el ETL tiene conectividad y credenciales para ambas; el API permanece limitado a OLTP.

**Q-026 — P0. ¿Se requiere un ETL con AWS Glue, o se acepta otro servicio disponible en Learner Lab?** Opciones a comparar después: Glue Spark; Lambda; script en EC2; otra. AWS DMS no aparece entre los servicios permitidos en el README suministrado.

> **Respuesta:** Se utilizará AWS Glue con el `LabRole` preexistente y sin crear o modificar IAM, sujeto al spike de `iam:PassRole` y conectividad. El ETL tendrá concurrencia 1, capacidad mínima permitida y ejecución automática cada hora mediante un trigger `SCHEDULED`.

## 3. Definición del negocio y requisitos funcionales

### Operación de la aerolínea

**Q-027. ¿Cuál es el tamaño supuesto de la aerolínea?** Indicar número inicial de aeropuertos, rutas, aeronaves, vuelos diarios, pasajeros diarios y reservas diarias; incluir un pico esperado.

> **Respuesta propuesta:** Aerolínea regional pequeña con 8 aeropuertos, 12 rutas directas, 4 aeronaves, 24 instancias de vuelo al día, 500 pasajeros y 250 reservas diarias. El pico estacional supuesto es 5 veces la tasa normal de búsquedas y 3 veces la tasa normal de creación de reservas. Son supuestos de dimensionamiento, no datos reales, y deben permanecer consistentes con los NFR y pruebas.

**Q-028. ¿Qué horizonte de venta se permite?** Ejemplo: desde hoy hasta 330 días; definir también cuánto tiempo antes de la salida deja de venderse.

> **Respuesta propuesta:** Se pueden buscar y reservar vuelos desde el momento actual hasta 180 días en el futuro. La venta se cierra 60 minutos antes de la salida local del primer segmento; una búsqueda puede mostrar el vuelo después de ese punto como no reservable, pero la creación de reserva debe rechazarlo.

**Q-029. ¿Cómo se identifican los vuelos recurrentes y sus ejecuciones?** Ejemplo: número comercial/schedule repetible + instancia fechada; definir zona horaria de salida y llegada.

> **Respuesta propuesta:** `ScheduledFlight` representa el vuelo comercial recurrente mediante número de vuelo y días de operación. Contiene uno o más `ScheduledLeg` ordenados, cada uno con origen, destino y horas locales; así un mismo número de vuelo puede tener escalas. `FlightInstance` representa la ejecución fechada del vuelo y contiene `FlightLegInstance` operacionales, con aeronave, salida/llegada UTC, estado e inventario por cabina. Cada aeropuerto conserva una zona IANA para convertir horarios locales de forma inequívoca.

**Q-030. ¿Qué estados puede tener una instancia de vuelo?** Ejemplos: programado, demorado, cancelado, en vuelo y completado.

> **Respuesta propuesta:** `SCHEDULED`, `DELAYED`, `BOARDING`, `DEPARTED`, `COMPLETED` y `CANCELLED`. Solo `SCHEDULED` y `DELAYED` aceptan nuevas reservas antes del cierre de venta. `BOARDING` y estados posteriores son de solo lectura para el flujo comercial.

**Q-031. ¿Qué condiciones hacen válida una conexión?** Definir tiempo mínimo/máximo de conexión, si debe ser el mismo aeropuerto y si se permiten cambios de aeropuerto.

> **Respuesta propuesta:** Los segmentos deben ser contiguos: el destino de un segmento es el origen del siguiente. La conexión ocurre en el mismo aeropuerto, sin traslado terrestre, con espera mínima de 45 minutos y máxima de 6 horas medida entre llegada y siguiente salida. No se aceptan ciclos ni regreso al aeropuerto de origen dentro del mismo itinerario de ida.

**Q-032. ¿Cuántos segmentos máximos tendrá un itinerario en el MVP?**

> **Respuesta propuesta:** Máximo 2 segmentos, es decir, vuelo directo o una conexión. Esto demuestra el modelo multi-leg sin introducir un algoritmo general de ruteo difícil de completar y defender para el MVP.

**Q-033. ¿La búsqueda es solo ida o también ida y vuelta?** Definir filtros obligatorios y opcionales: origen, destino, fecha, pasajeros, cabina, escalas, precio.

> **Respuesta propuesta:** El MVP busca solo itinerarios de ida; un regreso se maneja como otra reserva. Son obligatorios origen, destino, fecha local, número de pasajeros y cabina. Son opcionales máximo de escalas y precio máximo. El resultado muestra segmentos ordenados, horarios locales, disponibilidad mínima del itinerario, tarifa total y vigencia de la cotización. Origen y destino deben ser distintos y la cantidad de pasajeros debe estar entre 1 y 9.

**Q-034. ¿Cómo se manejan adultos, niños e infantes?** Si queda fuera del MVP, declarar que todos los pasajeros consumen una silla y usan la misma regla tarifaria.

> **Respuesta propuesta:** El MVP solo maneja pasajeros que consumen una silla y aplica la misma regla tarifaria; no distingue adultos, niños o infantes. Las categorías etarias y los infantes sin silla quedan fuera de alcance para evitar excepciones de inventario no requeridas.

### Reservas, pasajeros y sillas

**Q-035. ¿Una reserva puede contener varios pasajeros?** Si sí, indicar límites y si todos comparten itinerario y tarifa.

> **Respuesta propuesta:** Sí, entre 1 y 9 pasajeros. Todos comparten el mismo itinerario y cabina. El precio se guarda como snapshot por pasajero y segmento, permitiendo explicar el total aunque la tarifa base cambie después. La reserva solo se crea si hay cupo simultáneo para todos en todos los segmentos.

**Q-036. ¿Qué datos mínimos se guardan del comprador y de cada pasajero?** Evitar datos que no sean necesarios para la demostración.

> **Respuesta propuesta:** Del comprador: nombre, correo electrónico y teléfono opcional. De cada pasajero: nombres, apellidos, tipo y número de documento, nacionalidad opcional. Para el ejercicio se usarán únicamente datos sintéticos. No se almacenan datos de tarjeta, dirección, fecha de nacimiento ni información de salud.

**Q-037. ¿Se exige registro/autenticación o se puede reservar como invitado?** Definir también cómo se consulta una reserva: cuenta; código + apellido; otro.

> **Respuesta propuesta:** El pasajero reserva como invitado y consulta mediante localizador único más apellido de un pasajero. La autenticación completa queda fuera del MVP. Los flujos de agencia, administración y personal aeroportuario usan identidades simuladas de datos semilla y encabezados de prueba, y solo se expondrán durante pruebas controladas; esta limitación deberá declararse en seguridad.

**Q-038. ¿Cuándo se asigna una silla física?** Opciones: al reservar; opcional al comprar; en check-in; no se implementa y solo se controla capacidad por cabina.

> **Respuesta propuesta:** En el MVP se asigna automáticamente una silla disponible de la cabina en cada instancia de tramo al crear la retención. La asignación queda `HELD` hasta el pago y pasa a `ASSIGNED` al confirmar; se libera al expirar, fallar el pago o cancelar. Se intentará conservar la misma silla en tramos consecutivos del mismo vuelo, pero la garantía obligatoria es tener una silla válida por tramo. No se implementa selección visual ni check-in.

**Q-039. ¿Puede una aeronave cambiar después de vender reservas?** Si sí, definir qué pasa si la nueva aeronave tiene menos capacidad o un mapa de sillas diferente.

> **Respuesta propuesta:** El administrador puede cambiar la aeronave solo si la nueva tiene capacidad suficiente por cabina y las asignaciones activas pueden remapearse sin duplicados. En el MVP, si no se cumple, la operación se rechaza con conflicto y requiere resolución manual; no se cancela ni degrada automáticamente a pasajeros.

**Q-040. ¿Cuáles son los estados de reserva y transiciones válidas?** Propuesta para discutir: `PENDING_PAYMENT`, `CONFIRMED`, `CANCELLED`, `EXPIRED`.

> **Respuesta propuesta:** Estados: `PENDING_PAYMENT`, `CONFIRMED`, `PAYMENT_FAILED`, `CANCELLED` y `EXPIRED`. Transiciones permitidas: creación → `PENDING_PAYMENT`; pago aprobado vigente → `CONFIRMED`; pago rechazado → `PAYMENT_FAILED`; vencimiento → `EXPIRED`; cancelación solicitada desde `PENDING_PAYMENT` o `CONFIRMED` → `CANCELLED`. Los estados terminales no pueden reactivarse. Cada transición registra fecha, actor, motivo y estado anterior/nuevo.

**Q-041. ¿La cancelación es total o puede ser por pasajero/segmento?** Definir plazo, penalidad, liberación de inventario y reembolso.

> **Respuesta propuesta:** Solo cancelación total de la reserva. Se permite hasta 24 horas antes del primer segmento. La penalidad académica será 10 % del valor aprobado; el 90 % restante se registra como reembolso simulado. Los tickets y cupones emitidos pasan a `VOID`. Una reserva pendiente se cancela sin penalidad ni reembolso y nunca genera tickets. La liberación de todas las sillas/cupos y el cambio de estado ocurren en una única transacción e idempotentemente.

**Q-042. ¿Se permiten cambios de fecha o vuelo?** Definir diferencia tarifaria, penalidad, atomicidad y qué ocurre si el nuevo vuelo pierde disponibilidad.

> **Respuesta propuesta:** No se permiten cambios en el MVP. El usuario debe cancelar según la política y crear una nueva reserva. Como extensión, un cambio requeriría reservar primero el nuevo itinerario y liberar el anterior dentro de una operación coordinada; no se implementará parcialmente.

**Q-043. ¿Qué debe pasar si falla el pago después de apartar inventario?**

> **Respuesta propuesta:** La reserva pasa a `PAYMENT_FAILED`, el intento queda `DECLINED` y se liberan inmediatamente todas las sillas/cupos en la misma transacción. Un nuevo intento exige una nueva reserva y una nueva validación de disponibilidad. Si existe un error técnico sin respuesta del sistema simulado, la reserva permanece `PENDING_PAYMENT` hasta su expiración y el reintento usa la misma clave idempotente.

**Q-044. ¿Qué idempotencia necesita `POST /reservations`?** Ejemplo recomendado: encabezado `Idempotency-Key` para que un reintento no cobre ni reserve dos veces.

> **Respuesta propuesta:** `POST /api/v1/reservations` exige `Idempotency-Key`, única por actor/canal durante 24 horas. Repetir la clave con el mismo payload devuelve la misma reserva y no descuenta inventario de nuevo; reutilizarla con un payload diferente responde `409 IDEMPOTENCY_KEY_REUSED`. Pago y cancelación también serán idempotentes por referencia de operación.

### Tarifas, pagos y agencias

**Q-045. ¿Cómo se calcula el precio?** Definir bandas de anticipación, economía/business, impuestos, cargos y vigencia de la cotización.

> **Respuesta propuesta:** Cada ruta/cabina tiene una tarifa base. Multiplicador por anticipación: más de 30 días = 0.80; entre 7 y 30 días = 1.00; menos de 7 días = 1.25. Business aplica además 1.80 sobre la base economy. Para el ejercicio se agrega un cargo aeroportuario fijo configurable y un impuesto simulado de 10 %, claramente identificado como regla académica, no fiscal real. La cotización vence a los 15 minutos y el precio definitivo se guarda como snapshot al crear la reserva.

**Q-046. ¿En qué moneda se almacena el dinero y qué monedas se muestran/cobran?** Definir redondeo y prohibir `float` para importes monetarios.

> **Respuesta propuesta:** Moneda única COP para precios y pagos; los costos AWS se documentan por separado en USD. Los importes se almacenan como `NUMERIC(14,2)` y se calculan con decimal, nunca `float`, redondeando a dos decimales con regla half-up. La conversión de moneda queda fuera del MVP.

**Q-047. ¿Una tarifa es por segmento, por pasajero o por itinerario completo?**

> **Respuesta propuesta:** La tarifa se calcula por pasajero y segmento. El total del itinerario es la suma de sus componentes, cargos e impuestos para todos los pasajeros. La reserva conserva cada componente para auditoría e ingresos por tarifa; no se recalcula retroactivamente si cambia la tarifa base.

**Q-048. ¿Cómo se representa el pago?** Definir si puede haber varios intentos, pagos parciales, reembolsos y referencia del proveedor.

> **Respuesta propuesta:** Una reserva puede tener varios `PaymentAttempt`, pero como máximo uno puede quedar `APPROVED`. No hay pagos parciales. Cada intento registra monto, moneda, estado, instante, referencia sintética única y clave idempotente. Una cancelación de reserva confirmada crea un registro de reembolso simulado vinculado al pago aprobado; nunca sobrescribe el historial original.

**Q-049. ¿Qué diferencias tiene una agencia frente a un pasajero?** Definir API/interfaz, comisión, descuento, crédito, límites, identificador y auditoría.

> **Respuesta propuesta:** La agencia usa el mismo flujo de disponibilidad e inventario, pero cada reserva registra `channel=AGENCY`, `agency_id` y `agent_id`. Recibe una comisión simulada de 5 % sobre la tarifa antes de impuestos, registrada para analítica sin cambiar el precio pagado por el pasajero. No hay crédito, cupos exclusivos ni descuentos en el MVP. Toda operación queda atribuida al agente.

**Q-050. ¿Las agencias usan la misma API versionada o una API B2B separada?** Justificar por reglas y seguridad, no solo por preferencia tecnológica.

> **Respuesta propuesta:** Se usa la misma API versionada `/api/v1`, con endpoints y servicio de dominio compartidos. El canal y la identidad de agencia se registran explícitamente. No se crea un microservicio/API B2B separado porque las reglas de inventario y reserva son las mismas y duplicarlas aumentaría el riesgo de inconsistencia; una separación futura puede hacerse en la capa de exposición/autorización.

**Q-051. ¿Qué elementos se declaran fuera de alcance?** Marcar: equipaje, check-in, programa de viajero frecuente, selección avanzada de sillas, notificaciones, cupones, comidas, códigos compartidos, pagos reales, otros.

> **Respuesta propuesta:** Quedan fuera de alcance: equipaje, check-in, programa de viajero frecuente, selección visual de sillas, notificaciones, cupones promocionales, comidas, códigos compartidos, pagos reales, múltiples monedas, categorías etarias, ida y vuelta en una reserva, más de una conexión, cancelación parcial, cambios de fecha/vuelo y autenticación completa. El cupón de vuelo que representa cada segmento de un ticket sí forma parte del modelo. También se incluyen asignación automática de silla, pago simulado, cancelación total y canal de agencia.

### Decisiones funcionales derivadas

Estas reglas convierten las respuestas en invariantes comprobables. Si alguna no representa la intención del equipo, debe corregirse antes de diseñar el esquema.

| ID | Invariante funcional |
|---|---|
| INV-01 | Para cada instancia de tramo de vuelo y cabina, `available = capacity - held - confirmed` nunca es negativo. |
| INV-02 | Una reserva multi-leg obtiene inventario para todos sus pasajeros en todos sus segmentos o no obtiene ninguno. |
| INV-03 | Una silla física no puede estar retenida o asignada dos veces en la misma instancia de tramo; puede reutilizarse en un tramo posterior no superpuesto. |
| INV-04 | Una retención vencida no cuenta como ocupación, aunque la limpieza en segundo plano todavía no haya actualizado su estado. |
| INV-05 | Repetir una reserva, pago o cancelación con la misma clave idempotente no repite sus efectos. |
| INV-06 | Expirar, cancelar o rechazar el pago libera todas las unidades asociadas exactamente una vez. |
| INV-07 | El precio confirmado es un snapshot y no cambia cuando cambia posteriormente la tarifa base. |
| INV-08 | Solo pagos aprobados de reservas confirmadas cuentan como ingreso bruto; los reembolsos se restan para calcular ingreso neto. |
| INV-09 | Las expiraciones y pagos rechazados no cuentan como cancelaciones voluntarias. |
| INV-10 | No se puede sustituir una aeronave si su capacidad o mapa de sillas invalida asignaciones activas. |
| INV-11 | Una reserva pendiente no tiene tickets; al aprobar el pago se emite exactamente un ticket por pasajero y un cupón por segmento. |
| INV-12 | Los tickets son inmutables: una cancelación cambia su estado a `VOID` y conserva su historial; no los elimina. |

#### Actores y funciones del MVP

| Actor | Funciones del MVP | Interfaz |
|---|---|---|
| Pasajero/comprador | Buscar, reservar, registrar pago simulado, consultar y cancelar totalmente. | Web simple y API. |
| Agente de agencia | Mismo flujo, con atribución de agencia/agente y comisión. | Misma API versionada; vista simple diferenciada. |
| Administrador | Gestionar catálogos operativos, consultar reservas y ejecutar expiración. | Endpoints administrativos. |
| Personal de aeropuerto | Consultar vuelo/tramo, pasajeros y sillas confirmadas. | Endpoint de solo lectura. |
| Sistema de pagos simulado | Registrar resultados de pago y reembolso. | Endpoint de simulación idempotente. |
| Proceso ETL | Extraer OLTP y cargar OLAP. | Job AWS Glue. |
| Analista comercial | Consultar ingresos y cancelaciones. | SQL o reporte de evidencia sobre OLAP. |

## 4. Requisitos no funcionales medibles

Las respuestas deben incluir una métrica verificable y una condición de medición. “Rápido”, “seguro” o “escalable” no son métricas.

**Q-052 — Rendimiento. ¿Cuál es el objetivo de latencia de búsqueda?** Indicar p95/p99, volumen de datos, concurrencia y diferencia entre vuelo directo y conexiones.

> **Respuesta:** [POR RESPONDER]

**Q-053 — Rendimiento. ¿Cuál es el objetivo de latencia para crear y consultar una reserva?** Aclarar si el tiempo de un proveedor de pagos se excluye.

> **Respuesta:** [POR RESPONDER]

**Q-054 — Consistencia. ¿Cuál es la garantía exacta frente a la última silla?** Ejemplo verificable: con N solicitudes simultáneas y una unidad disponible, exactamente una confirma y las demás reciben conflicto; inventario nunca es negativo.

> **Respuesta propuesta:** Con una unidad disponible en cualquiera de los tramos solicitados y 20 solicitudes concurrentes equivalentes, exactamente una creación de reserva termina en `PENDING_PAYMENT`; las otras 19 reciben `409 INVENTORY_UNAVAILABLE`. Al finalizar, disponibilidad es 0, no hay contador negativo, no hay silla duplicada y no queda ninguna reserva parcial de otros tramos.

**Q-055 — Concurrencia. ¿Cuántas solicitudes simultáneas debe usar la prueba?** Indicar repeticiones y evidencia esperada.

> **Respuesta propuesta:** Veinte solicitudes simultáneas, repetidas 30 veces sobre datos reiniciados, tanto para un vuelo directo como para un itinerario de dos segmentos cuyo segundo tramo tiene la última silla. La prueba será de integración contra PostgreSQL real, no SQLite ni mocks, y verificará respuesta HTTP, conteos de estados, inventario, asignaciones y ausencia de reservas parciales.

**Q-056 — Disponibilidad. ¿Cuál es el objetivo conceptual de producción?** Elegir 99 %, 99.9 % o 99.99 % y definir ventana de medición. Aclarar por separado que Learner Lab no puede demostrar esa disponibilidad.

> **Respuesta:** [POR RESPONDER]

**Q-057 — Recuperación. ¿Cuáles son RTO y RPO para reservas y para OLAP?**

> **Respuesta:** [POR RESPONDER]

**Q-058 — Escalabilidad. ¿Cuál es el escenario de crecimiento?** Como mínimo responder al caso de 20 rutas nuevas/año; agregar multiplicador de búsquedas, reservas y datos.

> **Respuesta:** [POR RESPONDER]

**Q-059 — Seguridad. ¿Qué clasificación tendrán los datos?** Separar público, interno, PII y pago. No almacenar PAN/CVV aun si el pago es simulado.

> **Respuesta:** [POR RESPONDER]

**Q-060 — Seguridad. ¿Qué controles son verificables?** Ejemplos: TLS, cifrado en reposo al crear RDS, secretos fuera de Git, consultas parametrizadas, validación de entrada y ocultamiento de PII en logs. RDS PostgreSQL 15 o posterior exige SSL por defecto mediante `rds.force_ssl=1`, pero debe verificarse la versión y conexión usadas.[^4]

> **Respuesta:** [POR RESPONDER]

**Q-061 — Privacidad. ¿Qué regulación o política se asumirá?** Ejemplos: Ley 1581 de 2012/Habeas Data en Colombia para el ejercicio; PCI DSS queda fuera al delegar/simular pagos. Confirmar con el profesor; esto no constituye asesoría legal.

> **Respuesta:** [POR RESPONDER]

**Q-062 — Auditabilidad. ¿Qué eventos deben reconstruirse y por cuánto tiempo?** Incluir actor, instante, estado anterior/nuevo y correlación de solicitud.

> **Respuesta:** [POR RESPONDER]

**Q-063 — Observabilidad. ¿Qué logs, métricas y alarmas mínimas producirán evidencia?** Evitar PII y secretos.

> **Respuesta:** [POR RESPONDER]

**Q-064 — Mantenibilidad. ¿Qué umbral de calidad se exigirá?** Ejemplos: cobertura mínima, lint, migraciones reproducibles y documentación OpenAPI.

> **Respuesta:** [POR RESPONDER]

**Q-065 — Portabilidad/reproducibilidad. ¿Debe todo el entorno local ejecutarse con Docker Compose?** Indicar sistemas operativos de los miembros y restricciones de herramientas.

> **Respuesta:** [POR RESPONDER]

## 5. Modelo de datos transaccional

**Q-066. Elegir notación del diagrama ER:** Crow's Foot o Chen.

> **Respuesta:** [POR RESPONDER]

**Q-067. ¿Qué entidades adicionales a Flight, Aircraft, Route, Airport, Passenger, Reservation, Fare, Seat y Payment se aceptan?** Evaluar `FlightSchedule`, `FlightInstance`, `Itinerary`, `ItinerarySegment`, `ReservationPassenger`, `SeatInventory`, `Agency`, `PaymentAttempt` y `AuditEvent`.

> **Respuesta:** [POR RESPONDER]

**Q-068. ¿Qué significa “Route”?** Opción A: par origen-destino directo. Opción B: recorrido comercial con varios legs. Evitar que Route, itinerario y segmento representen lo mismo.

> **Respuesta:** [POR RESPONDER]

**Q-069. ¿Qué clave identifica una instancia única de vuelo?** Definir UUID/entero, número de vuelo, fecha operacional y zona horaria.

> **Respuesta:** [POR RESPONDER]

**Q-070. ¿Cómo se modela capacidad versus silla física?** Precisar restricciones únicas y claves foráneas que impiden asignar la misma silla dos veces en una instancia de vuelo.

> **Respuesta:** [POR RESPONDER]

**Q-071. ¿Dónde vive el contador o conjunto de inventario?** Indicar fila que se bloqueará/versionará y cómo se deriva o reconcilia la disponibilidad.

> **Respuesta:** [POR RESPONDER]

**Q-072. ¿Qué restricciones deben existir en la base, además de validaciones de API?** Ejemplos: capacidad no negativa, estados válidos, importes no negativos, unicidad de localizador y sillas, orden único de segmento.

> **Respuesta:** [POR RESPONDER]

**Q-073. ¿Qué estrategia de identificadores se usará?** UUID, BIGINT o combinación; justificar impacto en API, índices y ETL.

> **Respuesta:** [POR RESPONDER]

**Q-074. ¿Cómo se almacenan fecha/hora y zona horaria?** Propuesta a evaluar: instantes en UTC, zona IANA del aeropuerto y fecha local de operación explícita.

> **Respuesta:** [POR RESPONDER]

**Q-075. ¿Qué nivel de normalización tendrá OLTP?** Indicar excepciones y por qué no rompen consistencia.

> **Respuesta:** [POR RESPONDER]

**Q-076. ¿Se borran físicamente pasajeros/reservas o se conservan estados y auditoría?** Definir anonimización y retención.

> **Respuesta:** [POR RESPONDER]

## 6. Backend, API y prueba de concurrencia

**Q-077. ¿Monolito modular o servicios separados para el MVP?** Relacionar la elección con plazo, costo, consistencia del inventario y capacidad de defensa oral.

> **Respuesta:** [POR RESPONDER]

**Q-078. ¿Qué versiones base se usarán?** Python, FastAPI, PostgreSQL, ORM/controlador y gestor de dependencias.

> **Respuesta:** [POR RESPONDER]

**Q-079. ¿API síncrona, asíncrona o mixta?** Justificar junto con controlador de PostgreSQL y estrategia de transacción.

> **Respuesta:** [POR RESPONDER]

**Q-080. ¿Cómo delimita la transacción la creación de reserva?** Describir inicio, lectura/bloqueo, descuento de inventario, persistencia, commit/rollback y relación con pago.

> **Respuesta:** [POR RESPONDER]

**Q-081. ¿Qué devuelve la API cuando pierde la carrera por la última silla?** Definir código HTTP, cuerpo estable y posibilidad de reintento.

> **Respuesta:** [POR RESPONDER]

**Q-082. ¿Cómo se evitan deadlocks al reservar itinerarios de varios segmentos?** Ejemplo: bloquear inventarios siempre en un orden canónico y mantener transacciones cortas.

> **Respuesta:** [POR RESPONDER]

**Q-083. ¿Cómo se probará concurrencia?** Definir herramienta (`pytest`, `httpx`, script, etc.), barrera simultánea, estado inicial, aserciones y repetición.

> **Respuesta:** [POR RESPONDER]

**Q-084. ¿Qué otras pruebas son obligatorias?** Marcar: unitarias; integración; API; migraciones; ETL; contrato/esquema; carga; recuperación.

> **Respuesta:** [POR RESPONDER]

**Q-085. ¿Cómo se sembrarán datos reproducibles?** Incluir al menos dos aeropuertos, ruta, aeronave, vuelos/instancias, tarifas, inventario y un caso con última silla.

> **Respuesta:** [POR RESPONDER]

**Q-086. ¿Cómo se autentica la API del MVP?** Si queda fuera, declarar la limitación y no exponer el backend públicamente durante más tiempo del necesario.

> **Respuesta:** [POR RESPONDER]

**Q-087. ¿Cómo se versiona la API y cómo se representan errores?**

> **Respuesta:** [POR RESPONDER]

## 7. Arquitectura frontend

**Q-088. ¿SPA o renderizado en servidor?** Relacionar con NFR, complejidad y si solo se diseña o también se implementa.

> **Respuesta:** [POR RESPONDER]

**Q-089. ¿Pasajero y agente usan la misma interfaz con capacidades por rol o aplicaciones separadas?**

> **Respuesta:** [POR RESPONDER]

**Q-090. ¿Cómo se avisa que una silla dejó de estar disponible?** Opciones: validación al confirmar; polling; SSE; WebSocket. No prometer “tiempo real” sin definir latencia.

> **Respuesta:** [POR RESPONDER]

**Q-091. ¿Qué idiomas, monedas y zonas horarias debe presentar la interfaz?**

> **Respuesta:** [POR RESPONDER]

**Q-092. ¿Qué requisitos mínimos de accesibilidad y compatibilidad se asumirán?**

> **Respuesta:** [POR RESPONDER]

## 8. OLAP, ETL y Glue Data Catalog

**Q-093. ¿Cuál será el grano de la tabla de hechos principal?** Ejemplos: una fila por pasajero-segmento; una fila por pago; una fila por cambio de estado.

> **Respuesta:** Se usan tres granos complementarios para evitar métricas ambiguas: `fact_sales_segment`, una fila por `reservation_item` (un pasajero en un tramo); `fact_reservation`, una fila por reserva; y `fact_leg_occupancy`, una fila por inventario tramo/cabina y momento de snapshot. Un bridge reserva-ruta permite filtrar cancelaciones multi-leg sin duplicar el hecho de reserva.

**Q-094. ¿Qué dimensiones requiere la pregunta analítica elegida?** Evaluar fecha, ruta, aeropuerto, vuelo, tarifa, cabina, agencia y pasajero anonimizado.

> **Respuesta:** Fecha con roles de reserva, salida y cancelación; ruta operacional; instancia de vuelo; cabina; banda de anticipación tarifaria; canal y agencia. No se crea dimensión pasajero porque no es necesaria para las preguntas elegidas y aumentaría exposición de PII.

**Q-095. ¿OLAP usará esquema estrella, copia normalizada o agregado?** Justificar respecto de consultas, volumen y claridad pedagógica.

> **Respuesta:** Esquema estrella en `analytics`, no copia normalizada del OLTP. Las claves surrogate estabilizan dimensiones y las claves `source_*` soportan linaje/upsert. El modelo prioriza consultas y reconciliación claras; la normalización del dominio permanece exclusivamente en `public`.

**Q-096. ¿Qué tablas/vistas exactas cruzan el ETL?** Indicar columnas, transformaciones y datos sensibles excluidos.

> **Respuesta:** Cruzan únicamente reservas, ítems de reserva, pagos aprobados, refunds, auditoría de estados, inventarios, instancias/tramos/vuelos programados, cabinas y agencias. La transformación produce dimensiones, hechos y bridge; excluye pasajeros, nombres/apellidos, documentos, actores, agentes, localizadores e idempotency keys. El catálogo OLTP se restringe a las doce tablas fuente permitidas.

**Q-097. ¿La carga será completa o incremental?** Para incremental, definir watermark/clave, actualizaciones, cancelaciones tardías y reejecución idempotente. Los bookmarks JDBC de Glue se basan en claves ordenables y capturan filas nuevas por lotes; no resuelven por sí solos actualizaciones o eliminaciones.[^5]

> **Respuesta:** El MVP hace snapshot completo set-based porque el volumen del laboratorio es pequeño y los estados se actualizan después de crear la fila. No usa bookmarks JDBC basados solo en `created_at`. Para el escenario 10x se migrará a extracción incremental guiada por `audit_events`, staging y merge de las entidades afectadas.

**Q-098. ¿Cómo se garantiza idempotencia del ETL?** Opciones: `UPSERT` por clave de negocio; reemplazo por partición; staging + merge; truncado y recarga para el demo.

> **Respuesta:** Cada ejecución recibe `run_id` y `snapshot_at`. Dimensiones y hechos hacen `UPSERT` por sus claves de origen; ocupación usa `(source_inventory_id, snapshot_at)`. Repetir un `run_id` exitoso con el mismo snapshot es no-op y reutilizarlo con otro snapshot se rechaza. PostgreSQL serializa corridas mediante advisory lock transaccional.

**Q-099. ¿Qué validaciones de calidad de datos se ejecutan?** Ejemplos: conteos, claves nulas/duplicadas, sumas de ingresos, integridad de fechas y reconciliación OLTP/OLAP.

> **Respuesta:** Conteos separados de reservas, ítems de venta e inventarios; FK dimensionales no nulas; capacidad mayor o igual a retenidos más confirmados; ausencia de claves fuente duplicadas; y reconciliación exacta en COP entre pagos `APPROVED`/refunds OLTP y su asignación en OLAP. El watermark solo avanza después de una corrida exitosa.

**Q-100. ¿Cuántas conexiones, crawlers y bases de catálogo Glue se crearán?** Para fuentes JDBC, Glue requiere una conexión; el crawler escribe metadatos, no copia los datos.[^6]

> **Respuesta:** Dos conexiones JDBC al mismo RDS/base —una identidad lógica para `public` y otra para `analytics`—, dos crawlers bajo demanda y dos bases de Glue Data Catalog: `airline_oltp` y `airline_analytics`. Se usa el `LabRole` preexistente y no se crean ni modifican recursos IAM.

**Q-101. ¿Se catalogarán todas las tablas o solo las necesarias?** Restringir el path JDBC reduce tiempo, costo y exposición de metadatos.

> **Respuesta:** El crawler OLTP cataloga explícitamente doce tablas fuente y no usa `public/%`; quedan fuera pasajeros, agentes, identidades demo, sillas y registros de idempotencia. El crawler analítico cataloga las dimensiones, hechos, bridge y tablas de control del schema `analytics`.

**Q-102. ¿Cómo se demostrará que ambas bases están catalogadas?** Ejemplos: captura/exportación de bases y tablas, schemas inferidos, ejecución de crawler y logs.

> **Respuesta:** Evidencia automatizada/local del schema y ETL, más exportación sanitizada de `get-databases`, `get-tables`, estado `ACTIVATED` del trigger horario, estados `SUCCEEDED` de ambos crawlers y del job, y una consulta a `analytics.etl_run` con conteos y reconciliación. No se capturan contraseñas ni propiedades sensibles de las conexiones.

**Q-103. ¿Qué dispara el ETL?** Manual, horario o evento. La opción debe corresponder a la frescura de Q-024 y al presupuesto.

> **Respuesta:** Trigger Glue `SCHEDULED`, activado por el script de despliegue después de subir el job, con expresión `cron(0 * * * ? *)`. Se ejecuta al minuto 0 de cada hora UTC y mantiene concurrencia máxima 1. No se implementa procesamiento casi en tiempo real porque las preguntas no lo requieren y multiplicaría costo y operación.

## 9. Verificación práctica de Learner Lab

Estas comprobaciones no implican cambiar IAM. Deben ejecutarse en una sesión controlada antes del despliegue completo y registrar únicamente resultados no sensibles.

**Q-104 — Cuenta. ¿`us-east-1` funciona y es la región elegida?**

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-105 — IAM de solo lectura. ¿`LabRole` y `LabInstanceProfile` aparecen como opciones existentes en EC2/Glue?** No abrir, editar ni adjuntar políticas.

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-106 — PassRole. ¿Se puede crear un Glue crawler/job seleccionando `LabRole` sin crear otro rol?** Si falla, copiar solo código y texto del error, sin credenciales.

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-107 — RDS. ¿Qué clases burstable micro y versiones PostgreSQL ofrece realmente la consola?** Verificar también mínimo de almacenamiento, Single-AZ y posibilidad de desactivar Enhanced Monitoring.

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-108 — VPC. ¿Qué VPC, subredes y grupos de seguridad preexistentes están disponibles?** Registrar IDs parcialmente anonimizados si el documento será público.

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-109 — Red Glue/RDS. ¿Puede Glue crear una conexión JDBC a PostgreSQL en la misma VPC?** Glue crea una ENI y necesita un grupo de seguridad con regla TCP autorreferenciada. Si el job accede a S3 desde la VPC, se requiere un endpoint S3; solo si necesita internet público se requiere NAT.[^7]

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-110 — Secretos. ¿La cuenta permite crear/leer un secreto de Secrets Manager mediante `LabRole`, sin cambios IAM?** Si no, definir alternativa que nunca comprometa contraseñas en Git.

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-111 — Glue. ¿La cuenta confirma workers permitidos, máximo 10 y concurrencia 1?** Registrar versión de Glue y capacidad mínima seleccionable.

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-112 — Infraestructura como código. ¿CloudFormation puede crear VPC/SG/EC2/RDS/Glue usando recursos existentes y sin declarar IAM?** Hacer primero un stack mínimo descartable.

> **Respuesta / evidencia:** [POR RESPONDER]

**Q-113 — Inventario. ¿Tag Editor y las consolas muestran recursos huérfanos o costosos en ambas regiones permitidas?**

> **Respuesta / evidencia:** [POR RESPONDER]

## 10. Despliegue, operación y costos

**Q-114. ¿Cuál opción de despliegue debe evaluarse primero?**

- A. Dos RDS PostgreSQL pequeños + una EC2 pequeña para FastAPI.
- B. Un RDS con dos bases lógicas + una EC2 para FastAPI, sujeto a aprobación académica.
- C. Una EC2 con FastAPI y dos PostgreSQL aislados en contenedores, sujeto a aprobación académica.
- D. Otra.

> **Respuesta:** [POR RESPONDER]

**Q-115. ¿La API debe estar accesible desde internet durante la defensa?** Si sí, durante cuánto tiempo y desde qué orígenes.

> **Respuesta:** [POR RESPONDER]

**Q-116. ¿Las bases deben ser privadas?** Recomendación: sí; FastAPI y Glue acceden por grupos de seguridad, nunca abrir PostgreSQL a `0.0.0.0/0`.

> **Respuesta:** [POR RESPONDER]

**Q-117. ¿Se acepta evitar NAT Gateway?** A USD 0.045/h, uno activo todo el mes ronda USD 32.85 antes de procesamiento e IPv4, por lo que podría consumir cerca del 73 % de los USD 45 restantes.[^8] Se evaluará endpoint gateway de S3 sin cargo horario y una topología sin salida pública para Glue.[^9]

> **Respuesta:** [POR RESPONDER]

**Q-118. ¿Cuál será el horario operativo de cada recurso?** Completar:

| Recurso | Horas por sesión | Sesiones previstas | Horas totales |
|---|---:|---:|---:|
| EC2/API | [POR RESPONDER] | [POR RESPONDER] | [POR RESPONDER] |
| PostgreSQL OLTP | [POR RESPONDER] | [POR RESPONDER] | [POR RESPONDER] |
| PostgreSQL OLAP | [POR RESPONDER] | [POR RESPONDER] | [POR RESPONDER] |
| Glue ETL | [POR RESPONDER] | [POR RESPONDER] | [POR RESPONDER] |
| Crawlers | [POR RESPONDER] | [POR RESPONDER] | [POR RESPONDER] |

**Q-119. ¿Qué recursos se detienen y cuáles se eliminan después de cada sesión?** Tener presente que RDS detenido conserva cobros de almacenamiento y se reactiva automáticamente tras siete días.[^10]

> **Respuesta:** [POR RESPONDER]

**Q-120. ¿Dónde se conserva la evidencia antes de destruir recursos?** Opciones: repositorio sin secretos; S3 pequeño; exportación local; capturas; dump PostgreSQL.

> **Respuesta:** [POR RESPONDER]

**Q-121. ¿Qué tags estándar se usarán?** Propuesta: `Project`, `Environment`, `Owner`, `ExpiresAt` y `CostCenter`.

> **Respuesta:** [POR RESPONDER]

**Q-122. ¿Cuál es el umbral de “no desplegar” según saldo nominal?** Ejemplo: no iniciar recursos nuevos si el saldo visible es menor que la reserva de seguridad más el costo máximo estimado de la sesión.

> **Respuesta:** [POR RESPONDER]

**Q-123. ¿Quién es responsable de verificar y apagar recursos al final de cada sesión?** Nombrar titular y respaldo.

> **Respuesta:** [POR RESPONDER]

## 11. Documentación, trazabilidad y defensa

**Q-124. ¿Qué formato se usará para el documento final?** Markdown convertido a PDF, Word, LaTeX u otro.

> **Respuesta:** [POR RESPONDER]

**Q-125. ¿Qué herramienta se usará para diagramas?** Debe permitir versionar fuente o exportación: Mermaid, PlantUML, draw.io, Lucidchart, otra.

> **Respuesta:** [POR RESPONDER]

**Q-126. ¿Cómo se repartirán las responsabilidades de defensa?** Todos deben poder defender todo, pero conviene asignar responsables de preparación y revisión cruzada.

> **Respuesta:** [POR RESPONDER]

**Q-127. ¿Cómo se registrarán decisiones y desviaciones?** Propuesta: ADRs breves con estado, contexto, alternativas, decisión, consecuencias y enlaces a FR/NFR.

> **Respuesta:** [POR RESPONDER]

**Q-128. ¿Cómo se mantendrá el prompt log exigido?** Registrar fecha, objetivo, prompt resumido, resultado utilizado y corrección humana; nunca incluir secretos ni el enlace firmado de Vocareum.

> **Respuesta:** [POR RESPONDER]

**Q-129. ¿Qué escenarios sorpresa se ensayarán para la defensa?** Incluir al menos: cambio de aeronave, pago tardío, cancelación parcial, caída de OLAP, pico 10x y restricción adicional de costo.

> **Respuesta:** [POR RESPONDER]

**Q-130. ¿Cuál es la definición de terminado para cada entrega?** Indicar aprobación interna, pruebas, evidencia, revisión de costos y capacidad de explicación oral.

> **Respuesta:** [POR RESPONDER]

## 12. Registro preliminar de riesgos de AWS Academy

Escala: probabilidad e impacto cualitativos. Este registro se actualizará después de Q-104 a Q-113.

| ID | Riesgo | Prob. | Impacto | Tratamiento preliminar |
|---|---|---:|---:|---|
| R-ACA-01 | Glue u otro servicio intenta crear/pasar un rol y falla por las restricciones IAM. | Alta | Alto | Spike temprano usando solo `LabRole`; prohibir IAM en IaC; conservar alternativa ETL compatible. |
| R-ACA-02 | El saldo con 8–12 h de retraso oculta gasto reciente y se supera el presupuesto. | Alta | Crítico | Libro de costos por horas, reserva de seguridad, recursos mínimos, no confiar en el saldo como alarma inmediata. |
| R-ACA-03 | Superar presupuesto o un límite de servicio desactiva la cuenta y borra recursos. | Media | Crítico | Backups/evidencia fuera de recursos efímeros; inventario previo; límites duros en configuración. |
| R-ACA-04 | RDS queda activo al cerrar sesión o se reinicia tras 7 días. | Alta | Alto | Responsable de apagado; revisión periódica; preferir destruir/recrear cuando sea aceptable. |
| R-ACA-05 | Un NAT Gateway consume ~USD 32.85/mes más datos/IP y agota el presupuesto. | Media | Alto | No crearlo por defecto; probar S3 gateway endpoint y acceso privado dentro de una VPC. |
| R-ACA-06 | Dos RDS 24/7 más EC2, almacenamiento e IPv4 exceden los USD 45 restantes. | Alta | Alto | Ejecución por horas, Single-AZ, micro, almacenamiento mínimo; comparar 2 instancias vs alternativas permitidas. |
| R-ACA-07 | `LabRole` tiene permisos amplios y no puede reducirse a mínimo privilegio. | Alta | Alto | Excepción documentada; aislamiento de red y DB; secretos fuera de código; cuenta solo educativa. |
| R-ACA-08 | Conexión Glue-RDS falla por ENI, subred, DNS, endpoint S3 o reglas SG. | Alta | Alto | Spike de conectividad antes del ETL; misma VPC/subred alcanzable; SG autorreferenciado; endpoint S3. |
| R-ACA-09 | Las restricciones reales cambiaron desde el README de 2025. | Media | Alto | Checklist Q-104–Q-113 y registro de fecha/captura de la consola actual. |
| R-ACA-10 | Cerrar la sesión detiene/reinicia EC2 y cambia su IP pública. | Alta | Medio | Usar DNS/endpoints; script reproducible; no basar integraciones en IP fija. |
| R-ACA-11 | La disponibilidad de producción elegida no puede demostrarse en Learner Lab. | Alta | Medio | Separar arquitectura objetivo y despliegue académico reducido; declarar el trade-off. |
| R-ACA-12 | El enlace de Vocareum con `vockey` se publica en Git o prompt log. | Media | Alto | No almacenar query string; citar la fuente como privada; rotar/revocar si fue expuesta. |
| R-ACA-13 | `Reset` elimina datos sin recuperar presupuesto. | Baja | Crítico | Restringir su uso; exportar evidencia y dumps; limpieza selectiva/recreación con IaC. |
| R-ACA-14 | Un crawler cataloga tablas o PII innecesarias. | Media | Medio | Restringir rutas/tablas JDBC y validar catálogo antes de capturas públicas. |
| R-ACA-15 | El incremental con bookmarks omite updates/cancelaciones. | Media | Alto | Diseñar watermark + `updated_at`, staging/merge o recarga completa controlada. |
| R-ACA-16 | Credenciales de PostgreSQL quedan en Git, logs, capturas o parámetros de plantilla. | Media | Crítico | Secrets Manager si la capacidad existe; variables locales ignoradas; sanitización automática. |
| R-ACA-17 | La creación parcial por CloudFormation deja recursos huérfanos facturables. | Media | Alto | Stack mínimo primero; inventario antes/después; outputs claros y runbook de limpieza. |
| R-ACA-18 | El laboratorio expira antes de obtener evidencia final. | Media | Crítico | Confirmar Q-010; capturar evidencia temprana; respaldar esquema, código y resultados. |

## 13. Criterios que guiarán la planeación posterior

Cuando estén respondidas las preguntas, la planeación deberá:

1. convertir decisiones de negocio en FR y NFR medibles;
2. trazar cada decisión de modelo/arquitectura a al menos un FR/NFR;
3. comparar alternativas sin asumir que el servicio más sofisticado es el mejor para un laboratorio de USD 50;
4. diferenciar explícitamente arquitectura de producción y despliegue académico reducido;
5. no depender de crear o modificar IAM;
6. incluir un spike de permisos y conectividad antes de construir el ETL;
7. definir un presupuesto tanto mensual —exigido por el parcial— como de gasto real hasta la entrega;
8. incluir escenario 10x, seis pilares Well-Architected, pruebas, evidencias, runbooks y criterios de salida.

Los seis pilares que se usarán son excelencia operativa, seguridad, confiabilidad, eficiencia del rendimiento, optimización de costos y sostenibilidad.[^11]

## 14. Salida esperada de la siguiente fase

Después de responder este documento se crearán, dentro del repositorio:

- plan de trabajo por fases, dependencias, responsables y criterios de terminado;
- backlog trazable de FR/NFR y decisiones abiertas;
- propuesta y comparación de arquitectura local/AWS;
- ADR de concurrencia y ADR de ETL;
- modelo de costos base y 10x con supuestos explícitos;
- plan de pruebas, evidencias y defensa;
- runbook de despliegue/apagado compatible con Learner Lab;
- registro de riesgos actualizado.

## 15. Inicio del registro de prompts

Este registro es deliberadamente resumido y no reproduce URLs firmadas, tokens ni credenciales.

| Fecha | Objetivo | Prompt resumido | Refinamiento/corrección humana o técnica | Uso del resultado |
|---|---|---|---|---|
| 2026-09-09 | Iniciar la planeación | Revisar el parcial y Learner Lab; preparar preguntas de definición; investigar IAM y riesgos de presupuesto de USD 50. | Separar descubrimiento de planeación definitiva; tratar IAM como prohibición absoluta del proyecto; omitir el `vockey` del enlace; distinguir costo mensual académico de gasto real disponible. | Creación de este cuestionario, condiciones confirmadas y registro preliminar de riesgos. |

## Fuentes

[^1]: Enunciado del parcial, [parcial12026-2-EN.docx.pdf](../parcial12026-2-EN.docx.pdf), secciones 1–8. Fuente local entregada con el proyecto.
[^2]: AWS Academy, *Learner Lab README*, secciones Environment Overview, Region restriction, Service usage and other restrictions, IAM, Glue, RDS, EC2 y Preserving your budget; instrucciones actualizadas el 24 de junio de 2025. Fuente privada proporcionada mediante un enlace firmado. El parámetro `vockey` se omite deliberadamente del repositorio.
[^3]: AWS, [Step 2: Create an IAM role for AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/create-an-iam-role.html). Describe los permisos que Glue necesita y el requisito de `iam:PassRole`; en este laboratorio no se ejecutará el paso de crear el rol.
[^4]: AWS, [Using SSL with a PostgreSQL DB instance](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html). Documentación de `rds.force_ssl` y sus valores por versión.
[^5]: AWS, [Tracking processed data using job bookmarks](https://docs.aws.amazon.com/glue/latest/dg/monitor-continuations.html) y [Using job bookmarks](https://docs.aws.amazon.com/glue/latest/dg/programming-etl-connect-bookmarks.html).
[^6]: AWS, [Supported data sources for crawling](https://docs.aws.amazon.com/glue/latest/dg/crawler-data-stores.html) y [Using crawlers to populate the Data Catalog](https://docs.aws.amazon.com/glue/latest/dg/add-crawler.html).
[^7]: AWS, [Connecting to a JDBC data store in a VPC](https://docs.aws.amazon.com/glue/latest/dg/connection-JDBC-VPC.html) y [Setting up network access to data stores](https://docs.aws.amazon.com/glue/latest/dg/start-connecting.html).
[^8]: AWS, [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/). Ejemplo de referencia de USD 0.045 por hora para NAT Gateway; confirmar tarifa de región al calcular la entrega final.
[^9]: AWS, [Pricing for NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html). Recomienda endpoints cuando el tráfico principal va a servicios AWS; el endpoint gateway de S3 no tiene cargo horario ni por procesamiento en el ejemplo oficial.
[^10]: AWS, [Stopping an Amazon RDS DB instance temporarily](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html). No cobra cómputo mientras está detenida, pero sí almacenamiento/backup/IP pública y reinicia la instancia tras siete días.
[^11]: AWS, [The pillars of the AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html).

### Nota sobre precios

AWS publica para Glue un precio de referencia de USD 0.44 por DPU-hora; el catálogo incluye gratis el primer millón de objetos y el primer millón de accesos, y los crawlers y jobs tienen mínimos de facturación.[^12] Esto sirve como guardrail, no como proyección final: la región, capacidad mínima realmente seleccionable, duración, número de ejecuciones y arquitectura aún dependen de las respuestas.

[^12]: AWS, [AWS Glue pricing](https://aws.amazon.com/glue/pricing/).
