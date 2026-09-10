#!/usr/bin/env bash
set -euo pipefail

: "${EC2_HOST:?Set EC2_HOST to the deployed API instance public IP or DNS}"
SSH_USER="${SSH_USER:-ec2-user}"
SSH_KEY_PATH="${SSH_KEY_PATH:-${HOME}/.ssh/airline-demo-key}"
TARGET_PERCENT="${TARGET_PERCENT:-30}"
CONCURRENCY="${CONCURRENCY:-8}"
START_DATE="${START_DATE:-2026-09-11}"
END_DATE="${END_DATE:-2026-09-20}"

[[ -f "${SSH_KEY_PATH}" ]] || { echo 'SSH_KEY_PATH does not exist' >&2; exit 2; }
[[ "${TARGET_PERCENT}" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo 'invalid TARGET_PERCENT' >&2; exit 2; }
[[ "${CONCURRENCY}" =~ ^[0-9]+$ ]] || { echo 'invalid CONCURRENCY' >&2; exit 2; }
[[ "${START_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo 'invalid START_DATE' >&2; exit 2; }
[[ "${END_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo 'invalid END_DATE' >&2; exit 2; }

ssh -i "${SSH_KEY_PATH}" "${SSH_USER}@${EC2_HOST}" \
  "docker rm -f airline-simulator 2>/dev/null || true; docker run -d --name airline-simulator --restart unless-stopped --network host --no-healthcheck --log-opt max-size=10m --log-opt max-file=3 airline-api:demo python -m airline_core.traffic_daemon --base-url http://127.0.0.1:8000 --start-date ${START_DATE} --end-date ${END_DATE} --target-percent ${TARGET_PERCENT} --concurrency ${CONCURRENCY} --arrival-min-seconds 10 --arrival-max-seconds 25 --think-min-seconds 5 --think-max-seconds 45"

echo "Continuous simulator started on ${EC2_HOST}; inspect with:"
echo "ssh -i ${SSH_KEY_PATH} ${SSH_USER}@${EC2_HOST} 'docker logs --tail 100 airline-simulator'"
