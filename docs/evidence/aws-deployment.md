# Evidencia de despliegue AWS

Fecha: 2026-09-10

Perfil: `academy-lab`

Región: `us-east-1`

Stack: `airline-demo`

## Infraestructura

- CloudFormation: `CREATE_COMPLETE`
- VPC: `vpc-06e2887e0abb5706c`
- EC2: `i-0bd5d7d21aec40f24`
- Dirección pública de la API: `http://44.198.192.232:8000`
- RDS: `airline-demo-database-jxs3z3w2q5tw`
- PostgreSQL: `16.10`, `db.t3.micro`, Single-AZ
- Llave EC2: `airline-demo-key`

Controles verificados después del despliegue:

- RDS `available`, cifrada y `PubliclyAccessible=false`;
- `MultiAZ=false` y `MonitoringInterval=0`;
- las subredes privadas no tienen ruta `0.0.0.0/0`;
- el security group de RDS no permite 5432 desde `0.0.0.0/0`;
- el contenedor `airline-api` está `running healthy`;
- `GET /api/v1/health` devuelve `status=ok`.

## Prueba funcional en AWS

Se ejecutó el ciclo completo sobre la API desplegada:

1. búsqueda BOG-CLO para 2026-09-20;
2. reserva de dos segmentos y asignación de asiento;
3. pago simulado aprobado por COP 418000;
4. emisión de un ticket con dos cupones;
5. cancelación con un reembolso;
6. liberación de todos los recursos de inventario.

El smoke test de health, OpenAPI, interfaz y JavaScript también finalizó correctamente.

No se guardaron credenciales ni la contraseña de RDS en este documento o en Git. La contraseña runtime permanece con modo restringido en `/opt/airline/runtime.env` dentro de la EC2.
