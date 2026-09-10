# Despliegue AWS Academy Learner Lab

La plantilla `infra/airline-learner-lab.yaml` está preparada para el perfil `academy-lab` en `us-east-1`. Crea una VPC aislada `10.42.0.0/16`, una subred pública para una EC2 pequeña y dos subredes privadas en zonas distintas para RDS PostgreSQL Single-AZ. No crea recursos IAM, NAT Gateway, balanceador ni Enhanced Monitoring.

La API recibe IPv4 pública para la demo y expone el puerto 8000. SSH queda limitado al `/32` del operador. PostgreSQL no recibe IP pública, no tiene ruta a Internet y solo acepta el puerto 5432 desde el security group de la API.

## Configuración verificada

Los valores no secretos están en `deploy/academy-lab.env.example`:

- perfil `academy-lab`, región `us-east-1`;
- Amazon Linux 2023 x86_64 `ami-0b5358cc8c5df0b02`, publicada el 9 de septiembre de 2026;
- llave EC2 existente `vockey`;
- EC2 `t3.micro`;
- RDS PostgreSQL `16.10`, `db.t3.micro`, 20 GB gp3.

Para personalizarlos sin versionar datos locales:

```bash
cp deploy/academy-lab.env.example deploy/academy-lab.env
```

`deploy/academy-lab.env` está ignorado por Git. No guardes ahí `DB_PASSWORD`.

## Preflight seguro

```bash
./deploy/academy-preflight.sh
```

El preflight solo lee AWS: valida identidad, AMI, llave, disponibilidad de EC2/RDS, inventaría recursos facturables y valida CloudFormation. No crea ni modifica recursos.

El inventario del 10 de septiembre de 2026 encontró en `us-east-1` una EC2 `t3.micro` ajena a este stack, con EBS e IPv4 elástica; no se reutiliza ni modifica. Su security group permite SSH desde Internet, por lo que conviene restringirlo cuando confirmes que no necesitas ese acceso. No había RDS ni NAT Gateways. Las subredes de la VPC por defecto son públicas, razón por la que esta solución crea subredes privadas propias.

## Crear el stack más adelante

No se necesita `LabInstanceProfile`: la carga del contenedor se hace por SSH y la aplicación no llama APIs de AWS. Así se evita `iam:PassRole` y el stack no incluye ningún recurso `AWS::IAM::*`.

Cuando decidas desplegar:

```bash
./deploy/create-stack.sh
```

El script obtiene el IPv4 público actual del operador, pide la contraseña RDS sin mostrarla, repite el preflight, crea el stack y espera sus outputs. También acepta variables explícitas:

```bash
OPERATOR_CIDR=203.0.113.10/32 KEY_NAME=vockey ./deploy/create-stack.sh
```

La contraseña viaja mediante un archivo temporal con modo `0600`, eliminado al terminar. CloudFormation marca el parámetro como `NoEcho`; se evita Secrets Manager por permisos y coste del Learner Lab.

Después del stack:

```bash
docker build -t airline-api:demo .
ssh -i /ruta/Labsuser.pem ec2-user@IP_PUBLICA 'cloud-init status --wait && docker info >/dev/null'
EC2_HOST=IP_PUBLICA \
DB_ENDPOINT=ENDPOINT_PRIVADO_RDS \
DB_USER=airline_admin \
DB_PASSWORD='valor-ingresado' \
SSH_KEY_PATH=/ruta/Labsuser.pem \
./deploy/ec2-run.sh
BASE_URL=http://IP_PUBLICA:8000 ./deploy/smoke-test.sh
```

Los valores `IP_PUBLICA` y `ENDPOINT_PRIVADO_RDS` aparecen en los outputs `ApiPublicAddress` y `DatabaseEndpoint`.

## Evidencia, parada y eliminación

Guarda health, OpenAPI, búsqueda, reserva, pago, cancelación y outputs con `tee` en `docs/evidence/`. Para una pausa breve, detén EC2 y RDS usando los outputs `ApiInstanceId` y `DatabaseIdentifier`; RDS se inicia automáticamente después de siete días.

Antes de eliminar, conserva un `pg_dump --format=custom` si lo necesitas y borra `/opt/airline/runtime.env` de EC2. Después elimina el stack y espera:

```bash
aws cloudformation delete-stack --profile academy-lab --region us-east-1 --stack-name airline-demo
aws cloudformation wait stack-delete-complete --profile academy-lab --region us-east-1 --stack-name airline-demo
```

La base usa `DeletionPolicy: Snapshot`: revisa y elimina manualmente el snapshot final cuando ya no lo necesites. Ejecuta de nuevo el inventario y comprueba EBS, IPv4 elásticas, snapshots y recursos de otras regiones.

## Coste y riesgos

Estimación de referencia para `us-east-1`, consultada el 9 de septiembre de 2026 y sin aplicar créditos del laboratorio:

| Recurso | Supuesto | 8 horas | 730 horas / mes |
|---|---:|---:|---:|
| EC2 `t3.micro` | USD 0.0104/h | USD 0.08 | USD 7.59 |
| IPv4 pública de EC2 | USD 0.005/h | USD 0.04 | USD 3.65 |
| EBS root gp3 | 8 GB × USD 0.08/GB-mes | USD 0.01 prorrateado | USD 0.64 |
| RDS PostgreSQL `db.t3.micro`, Single-AZ | USD 0.018/h | USD 0.14 | USD 13.14 |
| RDS gp3 | 20 GB × USD 0.115/GB-mes | USD 0.03 prorrateado | USD 2.30 |
| **Subtotal** | sin transferencia, snapshots ni impuestos | **≈ USD 0.30** | **≈ USD 27.32** |

Fuentes: [AWS EC2 T3](https://aws.amazon.com/ec2/instance-types/t3/), [AWS VPC IPv4](https://aws.amazon.com/vpc/pricing/), [AWS EBS](https://aws.amazon.com/ebs/pricing/) y [AWS Price List de RDS en us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/us-east-1/index.json). Confirma saldo y precio en Academy antes de crear el stack.

VPC, subredes, route tables, Internet Gateway y security groups no añaden coste por sí solos. La ventana corta solo se aproxima por prorrateo: EBS, almacenamiento RDS y snapshots siguen cobrando mientras existan. El riesgo principal es olvidar RDS, volúmenes, IPv4 o snapshots.
