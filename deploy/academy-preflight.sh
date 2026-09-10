#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${ACADEMY_CONFIG:-${ROOT_DIR}/deploy/academy-lab.env}"

AWS_PROFILE="${AWS_PROFILE:-academy-lab}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AMI_ID="${AMI_ID:-ami-0b5358cc8c5df0b02}"
KEY_NAME="${KEY_NAME:-airline-demo-key}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"
DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS:-db.t3.micro}"
DB_ENGINE_VERSION="${DB_ENGINE_VERSION:-16.10}"

if [[ -f "${CONFIG_FILE}" ]]; then
  # This is a local, gitignored operator configuration file.
  # shellcheck source=/dev/null
  source "${CONFIG_FILE}"
fi

command -v aws >/dev/null 2>&1 || { echo 'AWS CLI is required' >&2; exit 1; }

echo "Checking profile ${AWS_PROFILE} in ${AWS_REGION} (read-only)"
CALLER_ARN="$(aws sts get-caller-identity --profile "${AWS_PROFILE}" --query Arn --output text)"
echo "Caller identity: ${CALLER_ARN}"

AZ_COUNT="$(aws ec2 describe-availability-zones --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --filters Name=state,Values=available --query 'length(AvailabilityZones)' --output text)"
[[ "${AZ_COUNT}" -ge 2 ]] || { echo 'at least two available AZs are required for the RDS subnet group' >&2; exit 1; }

AMI_STATE="$(aws ec2 describe-images --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --image-ids "${AMI_ID}" --query 'Images[0].State' --output text)"
[[ "${AMI_STATE}" == available ]] || { echo "AMI ${AMI_ID} is not available in ${AWS_REGION}" >&2; exit 1; }

KEY_COUNT="$(aws ec2 describe-key-pairs --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --key-names "${KEY_NAME}" --query 'length(KeyPairs)' --output text)"
[[ "${KEY_COUNT}" -eq 1 ]] || { echo "EC2 key pair ${KEY_NAME} was not found" >&2; exit 1; }

OFFERING_COUNT="$(aws ec2 describe-instance-type-offerings --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --location-type availability-zone --filters "Name=instance-type,Values=${INSTANCE_TYPE}" --query 'length(InstanceTypeOfferings)' --output text)"
[[ "${OFFERING_COUNT}" -ge 2 ]] || { echo "${INSTANCE_TYPE} is not offered in enough AZs" >&2; exit 1; }

RDS_COUNT="$(aws rds describe-orderable-db-instance-options --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --engine postgres --engine-version "${DB_ENGINE_VERSION}" --db-instance-class "${DB_INSTANCE_CLASS}" --query 'length(OrderableDBInstanceOptions)' --output text)"
[[ "${RDS_COUNT}" -ge 1 ]] || {
  echo "PostgreSQL ${DB_ENGINE_VERSION} on ${DB_INSTANCE_CLASS} is not orderable in ${AWS_REGION}" >&2
  exit 1
}
RDS_GP3_COUNT="$(aws rds describe-orderable-db-instance-options --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --engine postgres --engine-version "${DB_ENGINE_VERSION}" --db-instance-class "${DB_INSTANCE_CLASS}" --query "length(OrderableDBInstanceOptions[?StorageType=='gp3'])" --output text)"
[[ "${RDS_GP3_COUNT}" -ge 1 ]] || { echo 'the selected RDS combination does not support gp3 storage' >&2; exit 1; }

EC2_COUNT="$(aws ec2 describe-instances --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --query "length(Reservations[].Instances[?State.Name!='terminated'][])" --output text)"
RDS_EXISTING="$(aws rds describe-db-instances --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --query 'length(DBInstances)' --output text)"
NAT_COUNT="$(aws ec2 describe-nat-gateways --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --query 'length(NatGateways)' --output text)"
EIP_COUNT="$(aws ec2 describe-addresses --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --query 'length(Addresses)' --output text)"
VOLUME_COUNT="$(aws ec2 describe-volumes --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --query 'length(Volumes)' --output text)"

echo "Existing billable inventory: EC2=${EC2_COUNT}, RDS=${RDS_EXISTING}, NAT=${NAT_COUNT}, EIP=${EIP_COUNT}, EBS=${VOLUME_COUNT}"

AWS_PROFILE="${AWS_PROFILE}" AWS_REGION="${AWS_REGION}" "${ROOT_DIR}/infra/validate.sh"
"${ROOT_DIR}/infra/validate-negative.sh"
echo "Preflight passed: AMI=${AMI_ID}, key=${KEY_NAME}, EC2=${INSTANCE_TYPE}, RDS=postgres-${DB_ENGINE_VERSION}/${DB_INSTANCE_CLASS}"
echo 'No AWS resources were created or modified.'
