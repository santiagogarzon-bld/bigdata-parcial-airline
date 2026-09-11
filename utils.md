
# Dar acceso al SG de ec2
CURRENT_PUBLIC_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')"

aws ec2 authorize-security-group-ingress \
  --region us-east-1 \
  --group-id sg-05d5a0b8bc3e9e12d \
  --ip-permissions \
  "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=${CURRENT_PUBLIC_IP}/32,Description='DBeaver desde PC personal'}]"



# comprobar conexion

# Iniciar conexion tunel ssh

ssh -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -i /home/nuvu-pc-n4gx/.ssh/airline-demo-key \
  -L 15432:airline-demo-database-jxs3z3w2q5tw.cofhc4lwfrpt.us-east-1.rds.amazonaws.com:5432 \
  -L 15433:airline-demo-analyticsdatabase-cogrj4fjivjv.cofhc4lwfrpt.us-east-1.rds.amazonaws.com:5432 \
  ec2-user@52.70.187.30




  aws glue get-connection \
  --region us-east-1 \
  --name airline-oltp-jdbc \
  --query 'Connection.ConnectionProperties.PASSWORD' \
  --output text



  aws glue get-connection \
  --region us-east-1 \
  --name airline-analytics-jdbc \
  --query 'Connection.ConnectionProperties.PASSWORD' \
  --output text

# Definición del precio de vuelo
tarifa ajustada = tarifa base × multiplicador de anticipación × multiplicador de cabina
impuesto = (tarifa ajustada + tasa aeroportuaria) × 10 %
precio final = tarifa ajustada + tasa aeroportuaria + impuesto