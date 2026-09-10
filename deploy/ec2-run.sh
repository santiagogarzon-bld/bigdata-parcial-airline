#!/usr/bin/env bash
set -euo pipefail
# Operator-run over SSH. Secrets remain in the caller's environment and are
# passed only to docker at runtime; this script never writes them to the repo.
: "${EC2_HOST:?Set EC2_HOST to the instance public IP/DNS}"
: "${DB_ENDPOINT:?Set DB_ENDPOINT to the RDS private endpoint}"
: "${DB_USER:?Set DB_USER from the stack parameter}"
: "${DB_PASSWORD:?Set DB_PASSWORD interactively; never commit it}"
SSH_USER="${SSH_USER:-ec2-user}"
[[ "${EC2_HOST}" =~ ^[A-Za-z0-9._:-]+$ ]] || { echo 'invalid EC2_HOST' >&2; exit 2; }
[[ "${DB_ENDPOINT}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'invalid DB_ENDPOINT' >&2; exit 2; }
[[ "${DB_USER}" =~ ^[A-Za-z][A-Za-z0-9_]{0,15}$ ]] || { echo 'invalid DB_USER' >&2; exit 2; }
[[ "${SSH_USER}" =~ ^[A-Za-z_][A-Za-z0-9_-]{0,31}$ ]] || { echo 'invalid SSH_USER' >&2; exit 2; }
SSH_TARGET="${SSH_USER}@${EC2_HOST}"
SSH_ARGS=()
if [[ -n "${SSH_KEY_PATH:-}" ]]; then
  [[ -f "${SSH_KEY_PATH}" ]] || { echo 'SSH_KEY_PATH does not exist' >&2; exit 2; }
  SSH_ARGS=(-i "${SSH_KEY_PATH}")
fi
DB_URL="$(DB_PASSWORD="${DB_PASSWORD}" DB_ENDPOINT="${DB_ENDPOINT}" DB_USER="${DB_USER}" python - <<'PY'
import os
from urllib.parse import quote
print(f"postgresql+psycopg://{quote(os.environ['DB_USER'], safe='')}:{quote(os.environ['DB_PASSWORD'], safe='')}@{os.environ['DB_ENDPOINT']}:5432/airline_oltp")
PY
)"
docker save airline-api:demo | gzip | ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" 'gunzip | docker load'
printf 'DATABASE_URL=%s\n' "${DB_URL}" | ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" 'umask 077; mkdir -p /opt/airline; cat > /opt/airline/runtime.env'
ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "docker rm -f airline-api 2>/dev/null || true; docker run -d --name airline-api --restart unless-stopped -p 8000:8000 --env-file /opt/airline/runtime.env airline-api:demo"
ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "docker exec airline-api python -m airline_core.persistence.bootstrap --with-demo-data"
echo "API disponible en http://${EC2_HOST}:8000; ejecuta BASE_URL=http://${EC2_HOST}:8000 ./deploy/smoke-test.sh"
