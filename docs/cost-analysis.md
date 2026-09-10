# Análisis riguroso de costos: aplicación y plataforma analítica

Fecha de corte: 2026-09-10  
Región: `us-east-1`  
Cuenta observada: AWS Academy Learner Lab `064424822757`  
Stack principal: `airline-demo` (`UPDATE_COMPLETE`)

## 1. Resumen ejecutivo

El costo mensual de lista de la solución actualmente desplegada, operando de
forma continua durante 730 horas y ejecutando el ETL cada hora, es de
**aproximadamente USD 67.41/mes**, antes de impuestos, créditos de Academy y
transferencia extraordinaria. De ese total:

- **USD 27.32/mes** corresponden a la aplicación transaccional;
- **USD 40.09/mes** son incrementales de la capa analítica;
- el principal costo analítico variable es Glue (**USD 23.38/mes** con el
  consumo observado de la primera corrida programada);
- las dos RDS representan **USD 30.88/mes** y son el mayor costo fijo conjunto.

La cifra publicada previamente en la documentación, USD 84.98/mes, sobreestima
Glue porque supone cinco minutos por corrida. AWS reportó `262 DPUSeconds` para
la corrida horaria real: 131 segundos con 2 DPU. La proyección medida de Glue es
por ello USD 23.38/mes, no USD 52.80/mes. Este valor debe tratarse como una
línea base temprana: solo existen dos ejecuciones y el tiempo crecerá con el
volumen porque el proceso hace un snapshot completo.

## 2. Alcance y método

Se combinaron cuatro fuentes:

1. inventario real obtenido de CloudFormation, EC2, EBS, RDS, Glue, S3,
   CloudWatch y Cost Explorer;
2. configuración declarada en `infra/airline-learner-lab.yaml`;
3. comportamiento del ETL en `analytics/glue_job.py`, `analytics/etl.py` y las
   migraciones analíticas;
4. precios públicos de lista de AWS para `us-east-1`.

La proyección usa 730 horas/mes. No descuenta Free Tier ni créditos del
Learner Lab: esos beneficios ocultan el costo económico y no son transferibles
a una cuenta normal. Cost Explorer todavía presenta costo neto casi cero por
créditos y rezago de facturación, por lo que no sirve aún como run-rate.

No se incluyen trabajo humano de desarrollo, soporte, impuestos, dominios,
CI/CD externo ni el otro EC2/EIP ajeno al stack que existe en la cuenta. Sí se
incluye la Elastic IP `airline-api-eip`, aunque fue creada manualmente fuera de
CloudFormation, porque está asociada a la instancia de este proyecto.

## 3. Inventario desplegado y generadores de costo

| Capa | Recurso observado | Configuración | Forma de cobro |
|---|---|---|---|
| Aplicación | EC2 `i-0bd5d7d21aec40f24` | `t3.micro`, Linux, encendida | segundo/hora de cómputo |
| Aplicación | EBS `vol-0dfbf08dec2aac6c0` | 8 GB gp3, 3,000 IOPS, sin cifrar | GB-mes aprovisionado |
| Red | EIP `52.70.187.30` | asociada a EC2 | hora de IPv4 pública |
| OLTP | RDS PostgreSQL 16.10 | `db.t3.micro`, Single-AZ, 20 GB gp3 | instancia-hora + GB-mes |
| OLAP | RDS PostgreSQL 16.10 | `db.t3.micro`, Single-AZ, 20 GB gp3 | instancia-hora + GB-mes |
| ETL | Glue 4.0 Spark | 2 workers G.1X = 2 DPU, cron horario | DPU-segundo, mínimo aplicable |
| Catálogo | 2 Glue databases, 25 tablas | muy por debajo de 1 millón de objetos | dentro del tramo gratuito |
| Descubrimiento | 2 crawlers JDBC | bajo demanda | DPU-tiempo de crawler |
| Artefactos | S3 versionado | un objeto de 4,957 bytes | GB-mes + solicitudes |
| Observabilidad | CloudWatch/Glue logs | cuatro grupos, 0 bytes reportados al corte | ingestión y retención |
| Red privada | VPC, subredes, IGW, SG, S3 gateway endpoint | sin NAT Gateway | sin tarifa horaria propia |

No hay NAT Gateway, balanceador, RDS Multi-AZ, Performance Insights de pago,
Enhanced Monitoring, snapshots manuales ni volúmenes EBS huérfanos asociados al
proyecto. Esas ausencias evitan costos importantes.

## 4. Run-rate mensual de la arquitectura actual

### 4.1 Aplicación transaccional

| Partida | Fórmula | USD/mes |
|---|---:|---:|
| EC2 `t3.micro` | 730 h × 0.0104 | 7.59 |
| IPv4 pública | 730 h × 0.005 | 3.65 |
| EBS gp3 | 8 GB × 0.08 | 0.64 |
| RDS OLTP, cómputo | 730 h × 0.018 | 13.14 |
| RDS OLTP, almacenamiento | 20 GB × 0.115 | 2.30 |
| **Subtotal aplicación** | | **27.32** |

### 4.2 Capa analítica incremental

| Partida | Fórmula | USD/mes |
|---|---:|---:|
| RDS OLAP, cómputo | 730 h × 0.018 | 13.14 |
| RDS OLAP, almacenamiento | 20 GB × 0.115 | 2.30 |
| Glue ETL horario observado | 730 × 262 DPU-s ÷ 3,600 × 0.44 | 23.38 |
| Dos crawlers semanales | 4.33 × 2 × 2 DPU × 10/60 h × 0.44 | 1.27 |
| Data Catalog | 27 objetos aprox.; menor a 1 millón | 0.00 |
| S3, solicitudes y CloudWatch | volumen actual despreciable | <0.01 |
| **Subtotal analítica** | | **40.09** |

| Total | USD/mes |
|---|---:|
| Aplicación + analítica | **67.41** |
| Proyección anual sin compromisos | **808.92** |

Los crawlers tardaron aproximadamente 396 s (OLTP) y 221 s (OLAP), calculados
desde sus eventos de inicio y finalización. Sin embargo, AWS aplica un mínimo
facturable de diez minutos a cada crawl: cada par cuesta aproximadamente USD
0.293. Se modelan semanalmente por prudencia, aunque actualmente no tienen
schedule. Si solo se ejecutan al cambiar el esquema, su costo mensual normal
será cercano a cero.

## 5. Costo unitario del proceso analítico

AWS registró dos corridas exitosas:

| Tipo | Tiempo de ejecución | DPU-segundos | Costo de lista |
|---|---:|---:|---:|
| Manual/inicial | 79 s | 159 | USD 0.0194 |
| Programada | 131 s | 262 | USD 0.0320 |

La corrida programada equivale a aproximadamente **USD 0.032 por refresh**.
Con 730 refreshes mensuales son USD 23.38. El costo no depende todavía de los
GB procesados, sino de DPU × duración; en esta escala domina el arranque de
Spark y la apertura de conectividad JDBC.

El ETL no es incremental. Importa 12 tablas OLTP mediante `postgres_fdw` y la
función PostgreSQL reconstruye/mezcla un snapshot completo. Por tanto, si el
volumen multiplica por diez y la parte de consulta domina el tiempo, el costo
de Glue puede acercarse a diez veces el actual; además aumentan carga e I/O en
ambas RDS. No hay evidencia suficiente para afirmar una relación perfectamente
lineal, por eso se presentan escenarios y no una falsa estimación puntual.

## 6. Escenarios

| Escenario | Supuesto de Glue | Total mensual | Incremento analítico |
|---|---:|---:|---:|
| Actual medido | horario, 262 DPU-s/run | **USD 67.41** | USD 40.09 |
| ETL diario | 30 runs × 262 DPU-s | **USD 44.99** | USD 17.67 |
| ETL cada 4 horas | 183 runs × 262 DPU-s | **USD 49.89** | USD 22.57 |
| ETL horario, 5 min | 730 × 2 DPU × 5 min | **USD 97.57** | USD 70.25 |
| ETL horario, 10× duración | 730 × 2,620 DPU-s | **USD 277.82** | USD 250.50 |

Los escenarios conservan dos RDS y crawlers semanales. En una demostración de
ocho horas, creando y eliminando todos los recursos el mismo día, la estimación
es aproximadamente **USD 1.02**: USD 0.30 de aplicación y USD 0.72 de
analítica, incluidos ocho jobs y una corrida de cada crawler. Si los recursos
no se eliminan, almacenamiento, IPv4 y bases siguen cobrando.

## 7. Hallazgos de eficiencia y riesgo

1. **Frecuencia desalineada con el uso académico.** El trigger está
   `ACTIVATED` cada hora. Si no existe consumidor que necesite frescura horaria,
   pasar a diario reduce aproximadamente USD 22.42/mes sin cambiar el modelo.
2. **Spark está sobredimensionado para orquestar una función SQL.** El job usa
   el mínimo práctico de 2 G.1X, pero la transformación ocurre en PostgreSQL.
   Glue paga principalmente el arranque de Spark. Lambda o una tarea programada
   en EC2 serían mucho más baratas, aunque cambiarían la arquitectura y podrían
   incumplir el requisito académico de usar Glue.
3. **RDS OLAP es costo fijo por aislamiento.** Cuesta USD 15.44/mes incluso sin
   jobs. Para laboratorio, alojar `analytics` en la RDS OLTP ahorraría ese monto,
   pero sacrifica aislamiento de fallos y rendimiento; no se recomienda si la
   separación física es requisito evaluado.
4. **El snapshot completo limita la economía a escala.** Antes de aumentar
   frecuencia o volumen debe implementarse CDC/eventos auditables o staging
   incremental con watermark confiable. Ahorra Glue y reduce interferencia en
   RDS.
5. **La EC2 está ampliamente ociosa.** En las horas observadas promedió
   aproximadamente 0.9–2.6% de CPU, con máximo puntual 44.6%. `t3.nano` podría
   ahorrar USD 3.80/mes, pero 0.5 GB es riesgoso para Docker, API y simulador.
   Se debe medir memoria dentro del host antes de cambiarla.
6. **La Elastic IP queda fuera del ciclo de vida del stack.** Cuesta USD
   3.65/mes tanto asociada como ociosa y puede sobrevivir a una eliminación de
   CloudFormation. Debe incluirse en el checklist de teardown.
7. **Parar no equivale a eliminar.** EC2 detenida conserva EBS e IPv4; RDS
   detenida conserva almacenamiento y AWS la reinicia automáticamente después
   de siete días. Con el trigger activo, los jobs pueden seguir iniciándose y
   fallar, generando costo sin producir datos.
8. **Logs sin retención explícita.** El volumen actual es nulo/despreciable,
   pero los grupos Glue no tienen una política declarada de expiración. A escala
   deben fijarse 7–30 días para evitar crecimiento indefinido.
9. **Cost Explorer no refleja el costo económico todavía.** Los costos visibles
   están cubiertos casi totalmente por beneficios/créditos y tienen retraso. El
   control presupuestal debe usar costo de lista y alarmas de presupuesto, no
   interpretar el USD 0 actual como gratuidad estructural.

## 8. Recomendación priorizada

| Prioridad | Acción | Ahorro potencial | Impacto |
|---|---|---:|---|
| Alta | Desactivar el trigger fuera de pruebas o cambiarlo a diario | ≈ USD 22.42/mes | frescura pasa de 1 h a 24 h |
| Alta | Automatizar teardown e inventario de EIP, RDS, EBS y snapshots | hasta casi USD 67.41/mes en inactividad | requiere recrear para la siguiente práctica |
| Alta | Crear Budget/anomalía de costo con umbrales bajos | evita gasto accidental | costo directo despreciable |
| Media | Ejecutar crawlers solo tras migraciones de schema | ≈ USD 1.27/mes | catálogo no cambia entre migraciones |
| Media | Diseñar extracción incremental antes de crecer | hasta 90% del Glue en escenario 10× | mayor complejidad de ingeniería |
| Baja | Evaluar EC2 ARM/t4g o nano después de medir memoria | USD 1–4/mes | cambio de AMI/build o menor margen |
| Condicional | Unificar OLTP/OLAP solo si se relaja el aislamiento | USD 15.44/mes | mayor contención y menor resiliencia |

Para conservar la arquitectura evaluable y bajar costo sin rediseño, la mejor
configuración es: dos RDS pequeñas, ETL Glue diario o bajo demanda, crawlers
  solo después de migraciones y eliminación completa al terminar el laboratorio.
Su run-rate sería aproximadamente **USD 44.99/mes**, o mucho menos si el stack
solo vive durante las ventanas de demostración.

## 9. Controles FinOps recomendados

- etiquetar también la EIP con `Project`, `Environment`, `Owner` y `ExpiresAt`;
- añadir los mismos tags a todos los recursos que los soporten y activar las
  cost allocation tags;
- alarma de presupuesto a USD 10 y USD 25 para el laboratorio;
- alarma si `Glue JobRunsFailed > 0` o si una corrida supera 300 segundos;
- alarma de frescura basada en `analytics.etl_run`, no solo en éxito de Glue;
- revisión semanal de EIP, volúmenes, snapshots y RDS fuera de CloudFormation;
- política de retención de 14 días para logs Glue durante el curso;
- registrar por corrida `DPUSeconds`, filas fuente/destino y costo estimado para
  obtener costo por mil reservas procesadas cuando exista volumen suficiente.

## 10. Fuentes y limitaciones

- AWS Glue Pricing: USD 0.44/DPU-hora y facturación por segundo, con mínimos
  según el tipo y versión de workload: <https://aws.amazon.com/glue/pricing/>.
- AWS VPC Pricing: USD 0.005/h por IPv4 pública usada u ociosa:
  <https://aws.amazon.com/vpc/pricing/>.
- AWS EC2 T3 / guía oficial de dimensionamiento: `t3.micro` Linux en
  `us-east-1`, USD 0.0104/h.
- AWS RDS PostgreSQL Price List `us-east-1`: `db.t3.micro` Single-AZ USD
  0.018/h; gp3 USD 0.115/GB-mes.
- AWS EBS gp3 `us-east-1`: USD 0.08/GB-mes para el nivel base.

Los precios son de lista y pueden cambiar. La muestra de Glue es pequeña; debe
recalcularse tras 30 corridas y después de cada aumento relevante de datos. La
transferencia entre las dos RDS se mantiene dentro de la misma región pero
están en AZ distintas (`us-east-1a` y `us-east-1b`); debe vigilarse el cargo de
transferencia regional a medida que el snapshot crezca, aunque hoy su volumen
es despreciable.
