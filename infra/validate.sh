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
if rg -n "JDBC_ENFORCE_SSL:\s*['\"]false|s3://airline-analytics-artifacts|job-bookmark-enable" "${TEMPLATE}"; then
  echo 'analytics template contains an insecure or stale Glue setting' >&2; exit 1
fi
for required_pattern in "Path:.*analytics/%" "FromPort: 0" "ToPort: 65535" "SourceSecurityGroupId: \{Ref: GlueSecurityGroup\}" "Connections:" "airline-oltp-jdbc" "airline-analytics-jdbc" "--source_connection_name" "--target_connection_name" "--source_catalog_database" "--target_catalog_database" "--target_schema"; do
  if ! rg -q -- "${required_pattern}" "${TEMPLATE}"; then
    echo "missing required Glue networking/crawler setting: ${required_pattern}" >&2
    exit 1
  fi
done
if rg -n -- "--(source|target)-(connection|catalog|schema)" "${TEMPLATE}"; then
  echo 'Glue custom arguments must use underscores for getResolvedOptions' >&2
  exit 1
fi
for source_table in reservations reservation_items payments refunds audit_events inventories flight_leg_instances flight_instances scheduled_flights scheduled_legs cabins agencies; do
  if ! rg -q "Path:.*public/${source_table}" "${TEMPLATE}"; then
    echo "OLTP crawler is missing minimized source table: ${source_table}" >&2
    exit 1
  fi
done
if rg -n "Path:.*public/%" "${TEMPLATE}"; then
  echo 'OLTP crawler must not catalog every public table' >&2
  exit 1
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
