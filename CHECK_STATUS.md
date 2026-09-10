# Verificación rápida de AWS Academy

Ejecutar después de iniciar el Learner Lab y actualizar las credenciales del
perfil `default`. Todos los recursos están en `us-east-1`.

## 1. Credenciales y stack

```bash
aws sts get-caller-identity --profile default

aws cloudformation describe-stacks \
  --profile default \
  --region us-east-1 \
  --stack-name airline-demo \
  --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}'
```

El stack debe aparecer como `CREATE_COMPLETE` o `UPDATE_COMPLETE`.

## 2. EC2 y Elastic IP

```bash
aws ec2 describe-instances \
  --profile default \
  --region us-east-1 \
  --instance-ids i-0bd5d7d21aec40f24 \
  --query 'Reservations[0].Instances[0].{State:State.Name,PublicIP:PublicIpAddress,PrivateIP:PrivateIpAddress}' \
  --output table

aws ec2 describe-instance-status \
  --profile default \
  --region us-east-1 \
  --include-all-instances \
  --instance-ids i-0bd5d7d21aec40f24 \
  --query 'InstanceStatuses[0].{State:InstanceState.Name,System:SystemStatus.Status,Instance:InstanceStatus.Status}' \
  --output table

aws ec2 describe-addresses \
  --profile default \
  --region us-east-1 \
  --allocation-ids eipalloc-0df2d77cb4978c4c6 \
  --query 'Addresses[0].{IP:PublicIp,Instance:InstanceId,Association:AssociationId}' \
  --output table
```

Resultado esperado: EC2 `running`, checks `ok` y Elastic IP `52.70.187.30`
asociada a `i-0bd5d7d21aec40f24`.

Si EC2 está detenida:

```bash
aws ec2 start-instances \
  --profile default \
  --region us-east-1 \
  --instance-ids i-0bd5d7d21aec40f24

aws ec2 wait instance-status-ok \
  --profile default \
  --region us-east-1 \
  --instance-ids i-0bd5d7d21aec40f24
```

Si la Elastic IP perdió su asociación:

```bash
aws ec2 associate-address \
  --profile default \
  --region us-east-1 \
  --instance-id i-0bd5d7d21aec40f24 \
  --allocation-id eipalloc-0df2d77cb4978c4c6
```

## 3. RDS PostgreSQL

```bash
aws rds describe-db-instances \
  --profile default \
  --region us-east-1 \
  --db-instance-identifier airline-demo-database-jxs3z3w2q5tw \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Port:Endpoint.Port,Version:EngineVersion}' \
  --output table
```

El estado esperado es `available`.

Si RDS está detenida:

```bash
aws rds start-db-instance \
  --profile default \
  --region us-east-1 \
  --db-instance-identifier airline-demo-database-jxs3z3w2q5tw

aws rds wait db-instance-available \
  --profile default \
  --region us-east-1 \
  --db-instance-identifier airline-demo-database-jxs3z3w2q5tw
```

## 4. API y contenedores

```bash
curl --fail --show-error --max-time 15 \
  http://52.70.187.30:8000/api/v1/health

ssh -i ~/.ssh/airline-demo-key ec2-user@52.70.187.30 \
  'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

La API debe devolver `status: ok`. Si los contenedores existen pero están
detenidos:

```bash
ssh -i ~/.ssh/airline-demo-key ec2-user@52.70.187.30 \
  'docker start airline-api airline-simulator'
```

## 5. Túnel hacia PostgreSQL

Mantener este comando abierto mientras se use `psql`, DBeaver o DataGrip:

```bash
ssh -i ~/.ssh/airline-demo-key \
  -N \
  -L 54330:airline-demo-database-jxs3z3w2q5tw.cofhc4lwfrpt.us-east-1.rds.amazonaws.com:5432 \
  ec2-user@52.70.187.30
```

Conectar desde otra terminal o desde el cliente gráfico usando:

```text
Host: 127.0.0.1
Port: 54330
Database: airline_oltp
User: airline_admin
```

No guardar la contraseña de PostgreSQL en este archivo ni en Git.

