# Capa analítica en AWS Academy

La arquitectura, el modelo, los controles y los diagramas se explican de forma
consolidada en el
[Diseño detallado de la capa analítica](../analytics-detailed-design.md).

La plantilla `infra/airline-learner-lab.yaml` conserva la RDS OLTP y crea una segunda RDS PostgreSQL privada para analítica. No crea recursos `AWS::IAM::*`. La base `airline_analytics` debe inicializarse con `analytics/bootstrap_warehouse.py` antes de ejecutar el ETL o su crawler.

## Recursos incluidos

- Dos bases lógicas de AWS Glue Data Catalog: `airline_oltp` y `airline_analytics`.
- El crawler OLTP se limita explícitamente a `reservations`, `reservation_items`, `payments`, `refunds`, `audit_events`, `inventories`, `flight_leg_instances`, `flight_instances`, `scheduled_flights`, `scheduled_legs`, `cabins` y `agencies`; no cataloga todo `public` ni tablas de pasajeros, agentes o idempotencia.
- Dos conexiones JDBC de Glue a endpoints RDS diferentes: OLTP y OLAP.
- Un crawler bajo demanda para cada zona del catálogo.
- Un Glue Job Spark 4.0, dos workers `G.1X` y una ejecución concurrente máxima. El job actual hace snapshot completo idempotente y no activa bookmarks JDBC.
- Un trigger Glue `SCHEDULED` con `cron(0 * * * ? *)`: ejecuta el ETL al minuto 0 de cada hora UTC.
- Security group dedicado para las ENI de Glue y una regla de entrada RDS limitada a ese grupo.
- Un bucket S3 privado, con bloqueo de acceso público, cifrado SSE-S3 y versionado, más un S3 Gateway VPC Endpoint para usarlo sin NAT Gateway.

El bucket es creado con nombre único por CloudFormation (`AnalyticsArtifactsBucket`); las rutas son `AnalyticsScriptKey` y `AnalyticsTempPrefix`. La plantilla no crea permisos IAM. `GlueRoleArn` debe apuntar al `LabRole` preexistente del laboratorio y debe tener permisos de Glue, CloudWatch Logs, EC2 ENI, JDBC/RDS y S3 para las rutas usadas.

## Despliegue

1. Copiar `deploy/academy-lab.env.example` a `deploy/academy-lab.env` y sustituir el account ID de `GLUE_ROLE_ARN` por el ARN real de `LabRole`. No guardar contraseñas en ese archivo.
2. Para un stack nuevo, ejecutar `./deploy/create-stack.sh`; CloudFormation crea el bucket privado y el job apunta al objeto `etl/analytics_job.py`. Después de crear el stack se debe ejecutar una vez `deploy/update-analytics-stack.sh` para subir ese objeto; el script acepta que el template ya esté actualizado.
3. Para un stack ya desplegado, definir `GLUE_ROLE_ARN` y `ANALYTICS_DB_MASTER_PASSWORD` al ejecutar `deploy/update-analytics-stack.sh`. El script preserva los demás parámetros, crea o actualiza la RDS OLAP, sube `analytics/glue_job.py` con SSE-S3 y activa el scheduler; no imprime secretos.

El script es repetible: si CloudFormation ya está actualizado, reconoce únicamente `No updates are to be performed`, omite la espera, vuelve a subir el objeto Glue y conserva o reactiva el scheduler. Otros errores de actualización abortan el proceso.
4. Ejecutar `./infra/validate.sh` y revisar `aws cloudformation validate-template` con el perfil del laboratorio.
5. Inicializar la RDS OLAP con `analytics/bootstrap_warehouse.py`. Construir y
   desplegar la imagen actualizada con el flujo existente. En OLTP,
   `alembic upgrade head` elimina el warehouse transicional; el crawler no
   sustituye la inicialización analítica. Antes de una
   actualización productiva se debe seguir la política de backup descrita en
   `backend/README.md`.
6. En Glue, ejecutar primero `airline-oltp-crawler` y `airline-analytics-crawler` cuando haya tablas creadas. Confirmar después que `airline-analytics-etl-hourly` está en estado `ACTIVATED`; el script de actualización realiza esta activación.

Ejemplo de actualización explícita cuando el stack ya existe:

```bash
aws cloudformation update-stack \
  --profile academy-lab --region us-east-1 --stack-name airline-demo \
  --template-body file://infra/airline-learner-lab.yaml \
  --parameters ParameterKey=GlueRoleArn,UsePreviousValue=false,ParameterValue="$GLUE_ROLE_ARN"
```

No se requiere `CAPABILITY_IAM` porque no se define ningún recurso IAM. Para una actualización real hay que enviar también todos los parámetros existentes con `UsePreviousValue=true` o sus valores explícitos.

## Validaciones posteriores

```bash
aws glue get-connection --name airline-oltp-jdbc --hide-password \
  --query 'Connection.{Name:Name,Type:ConnectionType,Subnet:PhysicalConnectionRequirements.SubnetId}' \
  --profile academy-lab --region us-east-1
aws glue get-crawler --name airline-analytics-crawler --profile academy-lab --region us-east-1
aws glue start-crawler --name airline-analytics-crawler --profile academy-lab --region us-east-1
aws glue get-trigger --name airline-analytics-etl-hourly \
  --query 'Trigger.{Type:Type,State:State,Schedule:Schedule}' \
  --profile academy-lab --region us-east-1
```

Comprobar que el trigger está `ACTIVATED`, que una corrida horaria del job llega a `SUCCEEDED`, que las tablas aparecen en `airline_analytics` y que la ejecución es idempotente. El job no debe exponerse a Internet: Glue usa las subredes privadas, el SG dedicado, la conexión RDS y el endpoint Gateway de S3.

El entrypoint Glue debe leer los argumentos con guion bajo requeridos por `getResolvedOptions`: `source_connection_name`, `target_connection_name`, `source_catalog_database`, `target_catalog_database` y `target_schema`.

## Coste y operación

El diseño evita NAT Gateway y endpoints Interface. La segunda RDS usa la clase mínima; los crawlers siguen bajo demanda y el job se ejecuta cada hora mientras el trigger permanezca activo. Para detener costos fuera de la ventana de trabajo sin eliminar infraestructura:

```bash
aws glue stop-trigger --name airline-analytics-etl-hourly \
  --profile academy-lab --region us-east-1
```

Para reanudar la programación, ejecutar el mismo comando con `start-trigger`.
