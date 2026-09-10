# Preflight de AWS Academy

Fecha: 2026-09-10

Perfil: `academy-lab`

Región seleccionada: `us-east-1`

Comprobaciones de solo lectura:

- la sesión STS del rol de laboratorio responde correctamente;
- hay al menos dos zonas de disponibilidad;
- Amazon Linux 2023 x86_64 `ami-0b5358cc8c5df0b02` está disponible;
- la llave `vockey` existe;
- `t3.micro` está ofrecida en suficientes zonas;
- PostgreSQL `16.10` con `db.t3.micro` y gp3 es una combinación ordenable;
- no había instancias RDS ni NAT Gateways;
- las subredes por defecto tienen asignación automática de IP pública y no se usan para RDS;
- ya existía una EC2 `t3.micro`, un volumen EBS y una IPv4 elástica ajenos al proyecto.

No se invocaron operaciones IAM. No se creó, actualizó ni eliminó ningún recurso AWS durante esta preparación.
