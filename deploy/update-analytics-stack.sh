#!/usr/bin/env bash
set -euo pipefail

# Safely adds/updates only the analytics resources on an existing stack. It
# never recreates the stack and never accepts or prints database credentials.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${ROOT_DIR}/infra/airline-learner-lab.yaml"
AWS_PROFILE="${AWS_PROFILE:-academy-lab}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-airline-demo}"
GLUE_ROLE_ARN="${GLUE_ROLE_ARN:-}"
ANALYTICS_SCRIPT_KEY="${ANALYTICS_SCRIPT_KEY:-etl/analytics_job.py}"
ANALYTICS_TEMP_PREFIX="${ANALYTICS_TEMP_PREFIX:-glue-temp/}"
ANALYTICS_ETL_FILE="${ANALYTICS_ETL_FILE:-${ROOT_DIR}/analytics/glue_job.py}"
[[ "${GLUE_ROLE_ARN}" =~ ^arn:[^:]+:iam::[0-9]{12}:role/.+$ ]] || {
  echo 'GLUE_ROLE_ARN must be the existing AWS Academy LabRole ARN' >&2
  exit 2
}
[[ "${ANALYTICS_SCRIPT_KEY}" != /* && "${ANALYTICS_SCRIPT_KEY}" != */ ]] || {
  echo 'ANALYTICS_SCRIPT_KEY must be a relative S3 object key' >&2
  exit 2
}
[[ "${ANALYTICS_TEMP_PREFIX}" != /* && "${ANALYTICS_TEMP_PREFIX}" == */ ]] || {
  echo 'ANALYTICS_TEMP_PREFIX must be a relative S3 prefix ending in /' >&2
  exit 2
}
[[ -f "${ANALYTICS_ETL_FILE}" ]] || {
  echo "Glue entrypoint not found: ${ANALYTICS_ETL_FILE}" >&2
  echo 'Set ANALYTICS_ETL_FILE only to the Glue-compatible entrypoint; do not upload analytics/etl.py.' >&2
  exit 2
}

command -v jq >/dev/null || { echo 'jq is required' >&2; exit 1; }
command -v aws >/dev/null || { echo 'aws CLI is required' >&2; exit 1; }
aws_args=(--profile "${AWS_PROFILE}" --region "${AWS_REGION}")
aws cloudformation describe-stacks "${aws_args[@]}" --stack-name "${STACK_NAME}" >/dev/null
PARAMETERS_FILE="$(mktemp)"
trap 'rm -f "${PARAMETERS_FILE}" "${PARAMETERS_FILE}.update.log"' EXIT
chmod 600 "${PARAMETERS_FILE}"

# Preserve every parameter from the deployed stack. New analytics parameters
# are explicit, while old values (including NoEcho parameters) stay server-side.
aws cloudformation describe-stacks "${aws_args[@]}" --stack-name "${STACK_NAME}" \
  --query 'Stacks[0].Parameters' --output json |
  jq --arg role "${GLUE_ROLE_ARN}" --arg key "${ANALYTICS_SCRIPT_KEY}" --arg temp "${ANALYTICS_TEMP_PREFIX}" '
    map({ParameterKey: .ParameterKey, UsePreviousValue: true})
    | map(select(.ParameterKey != "GlueRoleArn" and .ParameterKey != "AnalyticsScriptKey" and .ParameterKey != "AnalyticsTempPrefix"))
    + [
      {ParameterKey: "GlueRoleArn", ParameterValue: $role},
      {ParameterKey: "AnalyticsScriptKey", ParameterValue: $key},
      {ParameterKey: "AnalyticsTempPrefix", ParameterValue: $temp}
    ]' >"${PARAMETERS_FILE}"

aws cloudformation update-stack "${aws_args[@]}" --stack-name "${STACK_NAME}" \
  --template-body "file://${TEMPLATE}" --parameters "file://${PARAMETERS_FILE}" \
  >"${PARAMETERS_FILE}.update.log" 2>&1 || {
    if rg -q 'No updates are to be performed' "${PARAMETERS_FILE}.update.log"; then
      echo 'CloudFormation already matches the requested template; continuing with ETL upload.'
    else
      cat "${PARAMETERS_FILE}.update.log" >&2
      exit 1
    fi
  }
if ! rg -q 'No updates are to be performed' "${PARAMETERS_FILE}.update.log"; then
  aws cloudformation wait stack-update-complete "${aws_args[@]}" --stack-name "${STACK_NAME}"
fi

BUCKET="$(aws cloudformation describe-stacks "${aws_args[@]}" --stack-name "${STACK_NAME}" \
  --query 'Stacks[0].Outputs[?OutputKey==`AnalyticsArtifactsBucketName`].OutputValue' --output text)"
[[ -n "${BUCKET}" && "${BUCKET}" != None ]] || { echo 'analytics bucket output not found' >&2; exit 1; }
aws s3 cp "${ANALYTICS_ETL_FILE}" "s3://${BUCKET}/${ANALYTICS_SCRIPT_KEY}" \
  "${aws_args[@]}" --sse AES256
echo "Updated ${STACK_NAME}; uploaded ETL to s3://${BUCKET}/${ANALYTICS_SCRIPT_KEY}"
