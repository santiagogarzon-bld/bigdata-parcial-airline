#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${ROOT_DIR}/infra/airline-learner-lab.yaml"
check_forbidden() {
  local file="$1"
  rg -n 'AWS::IAM::|NatGateway|MultiAZ:\s*true|MonitoringInterval:\s*[1-9]|PubliclyAccessible:\s*true' "$file" || \
    rg -n -U 'FromPort:\s*5432.*?(CidrIp:\s*0\.0\.0\.0/0|CidrIpv6:\s*::/0)' "$file"
}
if check_forbidden "${TEMPLATE}"; then
  echo 'prohibited infrastructure pattern found' >&2; exit 1
fi
if rg -n --glob '!validate.sh' '(postgresql(\+psycopg)?://[^[:space:]<>{}]+:[^${<>{}[:space:]]{8,}@|AWS_SECRET_ACCESS_KEY\s*=|DB_MASTER_PASSWORD\s*=)' "${ROOT_DIR}/infra" "${ROOT_DIR}/deploy" 2>/dev/null; then
  echo 'possible hardcoded secret found' >&2; exit 1
fi
python - "${TEMPLATE}" <<'PY'
import sys
from pathlib import Path
import yaml
class Loader(yaml.SafeLoader): pass
Loader.add_multi_constructor('!', lambda loader, suffix, node: loader.construct_object(node))
yaml.compose(Path(sys.argv[1]).read_text(), Loader=Loader)
PY
if command -v aws >/dev/null 2>&1 && [[ -n "${AWS_REGION:-${AWS_DEFAULT_REGION:-}}" ]]; then
  aws_args=(--region "${AWS_REGION:-${AWS_DEFAULT_REGION}}")
  if [[ -n "${AWS_PROFILE:-}" ]]; then
    aws_args+=(--profile "${AWS_PROFILE}")
  fi
  aws cloudformation validate-template \
    --template-body "file://${TEMPLATE}" \
    "${aws_args[@]}" >/dev/null
fi
echo 'infrastructure validation passed'
