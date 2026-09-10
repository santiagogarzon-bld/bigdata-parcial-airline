# Despliegue AWS Academy Learner Lab

La plantilla `infra/airline-learner-lab.yaml` crea EC2 pequeña y RDS PostgreSQL privada Single-AZ. No crea IAM, NAT, balanceador ni Enhanced Monitoring.

## Preflight y despliegue

1. Usa solo `us-east-1` o `us-west-2`. En ambas regiones revisa identidad, saldo y recursos: `aws sts get-caller-identity`; `aws ec2 describe-vpcs --region "$r"`, `describe-subnets`, `describe-instances`, `describe-volumes`, `describe-addresses`; `aws rds describe-db-instances --region "$r"` y `describe-db-snapshots`. Conserva USD 30 de saldo y limita gasto adicional a USD 15.
2. Ejecuta `./infra/validate.sh` y `./infra/validate-negative.sh`.
3. Elige una AMI Amazon Linux compatible con `ec2-user`, `dnf` o `yum`, y SSH. El UserData instala/inicia Docker; la subred pública debe tener ruta a un Internet Gateway. Obtén CIDR local (`OPERATOR_CIDR="$(curl -fsS https://checkip.amazonaws.com)/32"`; se ejecuta localmente) y construye `docker build -t airline-api:demo .`.
   Antes del stack confirma `DBEngineVersion` disponible con `aws rds describe-db-engine-versions --engine postgres --engine-version 16.10 --region "$REGION"`. La contraseña usa `NoEcho` y entrada runtime deliberadamente; no se usa Secrets Manager por restricciones, permisos y coste del Learner Lab.
4. Crea el stack con variables completas y contraseña sin eco:

```bash
read -rsp 'DB password: ' DB_PASSWORD
echo
REGION=us-east-1
STACK=airline-demo
aws cloudformation create-stack --region "$REGION" --stack-name "$STACK" --template-body file://infra/airline-learner-lab.yaml \
  --parameters ParameterKey=VpcId,ParameterValue="$VPC_ID" ParameterKey=PublicSubnetId,ParameterValue="$PUBLIC_SUBNET_ID" \
  ParameterKey=PrivateSubnetA,ParameterValue="$PRIVATE_SUBNET_A" ParameterKey=PrivateSubnetB,ParameterValue="$PRIVATE_SUBNET_B" \
  ParameterKey=OperatorCidr,ParameterValue="$OPERATOR_CIDR" ParameterKey=AmiId,ParameterValue="$AMI_ID" \
  ParameterKey=LabInstanceProfile,ParameterValue="$LAB_INSTANCE_PROFILE" ParameterKey=InstanceType,ParameterValue=t3.micro \
  ParameterKey=DBInstanceClass,ParameterValue=db.t3.micro ParameterKey=DBMasterUsername,ParameterValue="$DB_USER" \
  ParameterKey=DBMasterPassword,ParameterValue="$DB_PASSWORD"
aws cloudformation wait stack-create-complete --region "$REGION" --stack-name "$STACK"
aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query 'Stacks[0].Outputs'
unset DB_PASSWORD
```

5. Espera el UserData con `ssh "ec2-user@$EC2_HOST" 'cloud-init status --wait && docker info >/dev/null'`. Define temporalmente `EC2_HOST`, `DB_ENDPOINT`, `DB_USER`, `DB_PASSWORD`; ejecuta `./deploy/ec2-run.sh` y después `BASE_URL=http://IP_PUBLICA:8000 ./deploy/smoke-test.sh`.

## Evidencia, parada y eliminación

Guarda health, OpenAPI, búsqueda, reserva, pago, cancelación y outputs (`tee evidence/*.json`). Para una pausa breve, detén EC2 (`aws ec2 stop-instances --region "$REGION" --instance-ids ...`) y RDS (`aws rds stop-db-instance --region "$REGION" --db-instance-identifier ...` usando el output `DatabaseIdentifier`); recuerda que RDS se inicia sola después de siete días. Haz `pg_dump --format=custom` si aplica. Para terminar, elimina primero `/opt/airline/runtime.env` en EC2 (`sudo shred -u /opt/airline/runtime.env`), luego elimina el stack y espera: `aws cloudformation delete-stack --region "$REGION" --stack-name "$STACK"`; `aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$STACK"`. Lista y elimina snapshots RDS, EIP y volúmenes no necesarios. Revisa saldo y costes en ambas regiones.

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

Fuentes: [AWS EC2 T3](https://aws.amazon.com/ec2/instance-types/t3/), [AWS VPC IPv4](https://aws.amazon.com/vpc/pricing/), [AWS EBS](https://aws.amazon.com/ebs/pricing/) y [AWS Price List de RDS en us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/us-east-1/index.json). Confirma de nuevo clase, versión, almacenamiento mínimo y precio en la consola o Pricing Calculator del Learner Lab antes de crear el stack.

La ventana corta solo se aproxima por prorrateo: EBS, almacenamiento RDS y snapshots siguen cobrando mientras existan, aunque el cómputo esté detenido. Una RDS detenida se inicia automáticamente tras siete días y vuelve a facturar cómputo. El riesgo principal no es la prueba de ocho horas sino olvidar RDS, volúmenes, IPv4 o snapshots; por eso el runbook exige eliminación e inventario final. No se desplegó AWS real durante esta tarea.
