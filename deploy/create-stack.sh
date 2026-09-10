#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${ACADEMY_CONFIG:-${ROOT_DIR}/deploy/academy-lab.env}"
TEMPLATE="${ROOT_DIR}/infra/airline-learner-lab.yaml"

AWS_PROFILE="${AWS_PROFILE:-academy-lab}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-airline-demo}"
AMI_ID="${AMI_ID:-ami-0b5358cc8c5df0b02}"
KEY_NAME="${KEY_NAME:-airline-demo-key}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"
DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS:-db.t3.micro}"
DB_ENGINE_VERSION="${DB_ENGINE_VERSION:-16.10}"
DB_NAME="${DB_NAME:-airline_oltp}"
DB_USER="${DB_USER:-airline_admin}"
ANALYTICS_DB_NAME="${ANALYTICS_DB_NAME:-airline_analytics}"
ANALYTICS_DB_INSTANCE_CLASS="${ANALYTICS_DB_INSTANCE_CLASS:-db.t3.micro}"
GLUE_ROLE_ARN="${GLUE_ROLE_ARN:-}"

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${CONFIG_FILE}"
fi

[[ "${GLUE_ROLE_ARN}" =~ ^arn:[^:]+:iam::[0-9]{12}:role/.+$ ]] || {
  echo 'GLUE_ROLE_ARN must be the existing AWS Academy LabRole ARN (no role is created)' >&2
  exit 2
}

if [[ -z "${OPERATOR_CIDR:-}" ]]; then
  OPERATOR_IP="$(curl --fail --silent --show-error https://checkip.amazonaws.com)"
  OPERATOR_CIDR="${OPERATOR_IP}/32"
fi
[[ "${OPERATOR_CIDR}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/32$ ]] || {
  echo 'OPERATOR_CIDR must be a public IPv4 address with /32' >&2
  exit 2
}

if [[ -z "${DB_PASSWORD:-}" ]]; then
  read -rsp 'RDS master password (16-41 characters): ' DB_PASSWORD
  echo
fi
[[ ${#DB_PASSWORD} -ge 16 && ${#DB_PASSWORD} -le 41 ]] || {
  echo 'DB_PASSWORD must contain 16-41 characters' >&2
  exit 2
}
if [[ "${DB_PASSWORD}" == *"/"* || "${DB_PASSWORD}" == *"@"* || "${DB_PASSWORD}" == *'"'* || "${DB_PASSWORD}" =~ [[:space:]] ]]; then
  echo 'DB_PASSWORD cannot contain whitespace, slash, at sign, or double quote' >&2
  exit 2
fi
if [[ -z "${ANALYTICS_DB_PASSWORD:-}" ]]; then
  read -rsp 'Analytical RDS master password (16-41 characters): ' ANALYTICS_DB_PASSWORD
  echo
fi
[[ ${#ANALYTICS_DB_PASSWORD} -ge 16 && ${#ANALYTICS_DB_PASSWORD} -le 41 ]] || {
  echo 'ANALYTICS_DB_PASSWORD must contain 16-41 characters' >&2
  exit 2
}

if aws cloudformation describe-stacks --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --stack-name "${STACK_NAME}" >/dev/null 2>&1; then
  echo "Stack ${STACK_NAME} already exists; this script intentionally does not update it." >&2
  exit 2
fi

AWS_PROFILE="${AWS_PROFILE}" AWS_REGION="${AWS_REGION}" AMI_ID="${AMI_ID}" KEY_NAME="${KEY_NAME}" \
  INSTANCE_TYPE="${INSTANCE_TYPE}" DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS}" \
  DB_ENGINE_VERSION="${DB_ENGINE_VERSION}" "${ROOT_DIR}/deploy/academy-preflight.sh"

command -v jq >/dev/null 2>&1 || { echo 'jq is required to encode stack parameters safely' >&2; exit 1; }
PARAMETERS_FILE="$(mktemp)"
trap 'rm -f "${PARAMETERS_FILE}"; unset DB_PASSWORD ANALYTICS_DB_PASSWORD' EXIT
chmod 600 "${PARAMETERS_FILE}"
jq -n \
  --arg operator "${OPERATOR_CIDR}" \
  --arg key "${KEY_NAME}" \
  --arg ami "${AMI_ID}" \
  --arg instance "${INSTANCE_TYPE}" \
  --arg db_class "${DB_INSTANCE_CLASS}" \
  --arg db_user "${DB_USER}" \
  --arg db_password "${DB_PASSWORD}" \
  --arg db_version "${DB_ENGINE_VERSION}" \
  --arg db_name "${DB_NAME}" \
  --arg analytics_db_name "${ANALYTICS_DB_NAME}" \
  --arg analytics_db_class "${ANALYTICS_DB_INSTANCE_CLASS}" \
  --arg analytics_db_password "${ANALYTICS_DB_PASSWORD}" \
  --arg glue_role_arn "${GLUE_ROLE_ARN}" \
  '[
    {ParameterKey:"OperatorCidr",ParameterValue:$operator},
    {ParameterKey:"KeyName",ParameterValue:$key},
    {ParameterKey:"AmiId",ParameterValue:$ami},
    {ParameterKey:"InstanceType",ParameterValue:$instance},
    {ParameterKey:"DBInstanceClass",ParameterValue:$db_class},
    {ParameterKey:"DBMasterUsername",ParameterValue:$db_user},
    {ParameterKey:"DBMasterPassword",ParameterValue:$db_password},
    {ParameterKey:"DBEngineVersion",ParameterValue:$db_version},
    {ParameterKey:"DBName",ParameterValue:$db_name},
    {ParameterKey:"AnalyticsDBName",ParameterValue:$analytics_db_name},
    {ParameterKey:"AnalyticsDBInstanceClass",ParameterValue:$analytics_db_class},
    {ParameterKey:"AnalyticsDBMasterPassword",ParameterValue:$analytics_db_password},
    {ParameterKey:"GlueRoleArn",ParameterValue:$glue_role_arn}
  ]' >"${PARAMETERS_FILE}"

echo "Creating ${STACK_NAME} in ${AWS_REGION}; this creates billable EC2, public IPv4, EBS and RDS resources."
aws cloudformation create-stack \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-body "file://${TEMPLATE}" \
  --parameters "file://${PARAMETERS_FILE}" \
  --tags Key=Project,Value=airline-oltp-mvp

rm -f "${PARAMETERS_FILE}"
unset DB_PASSWORD ANALYTICS_DB_PASSWORD
trap - EXIT

aws cloudformation wait stack-create-complete \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}"
aws cloudformation describe-stacks \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query 'Stacks[0].Outputs' \
  --output table
