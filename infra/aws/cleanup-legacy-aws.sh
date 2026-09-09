#!/usr/bin/env bash
# Remove orphaned Kong-era AWS resources (EIPs, Secrets Manager secrets, security groups).
# Safe to run before/after terraform apply. Idempotent.
#
# Usage:
#   bash infra/aws/cleanup-legacy-aws.sh
#   AWS_REGION=ap-south-1 NAME_PREFIX=get1agent-prod bash infra/aws/cleanup-legacy-aws.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AWS_REGION="${AWS_REGION:-us-east-1}"
NAME_PREFIX="${NAME_PREFIX:-get1agent-prod}"

echo "=== Legacy AWS cleanup (${NAME_PREFIX}, ${AWS_REGION}) ==="

echo ""
echo "--- Security groups ---"
bash "$ROOT/infra/aws/cleanup-stale-security-groups.sh"

delete_orphan_sg() {
  local name="$1"
  local sg_id
  sg_id="$(aws ec2 describe-security-groups \
    --region "$AWS_REGION" \
    --filters "Name=group-name,Values=${name}" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None")"

  if [[ "$sg_id" == "None" || -z "$sg_id" ]]; then
    echo "Security group ${name}: not found"
    return 0
  fi

  echo "Deleting security group ${name} (${sg_id})..."
  if aws ec2 delete-security-group --region "$AWS_REGION" --group-id "$sg_id" 2>/dev/null; then
    echo "Deleted ${name}"
  else
    echo "Could not delete ${name} (still referenced); skip"
  fi
}

delete_orphan_sg "${NAME_PREFIX}-kong"
delete_orphan_sg "${NAME_PREFIX}-app"

echo ""
echo "--- Elastic IPs (Kong-era) ---"
KONG_EIP_FOUND=0
while read -r alloc_id; do
  [[ -z "$alloc_id" || "$alloc_id" == "None" ]] && continue
  KONG_EIP_FOUND=1
  echo "Releasing Elastic IP ${alloc_id}..."
  aws ec2 release-address --region "$AWS_REGION" --allocation-id "$alloc_id" || true
done < <(aws ec2 describe-addresses \
  --region "$AWS_REGION" \
  --filters "Name=tag:Name,Values=${NAME_PREFIX}-kong-eip" \
  --query 'Addresses[].AllocationId' \
  --output text 2>/dev/null | tr '\t' '\n')

if [[ "$KONG_EIP_FOUND" -eq 0 ]]; then
  echo "No Kong-era Elastic IPs found"
fi

# Release any other unattached EIPs tagged with this project prefix.
while IFS=$'\t' read -r alloc_id name_tag; do
  [[ -z "$alloc_id" || "$alloc_id" == "None" ]] && continue
  [[ "$name_tag" != "${NAME_PREFIX}"* ]] && continue
  echo "Releasing unattached Elastic IP ${alloc_id} (${name_tag})..."
  aws ec2 release-address --region "$AWS_REGION" --allocation-id "$alloc_id" || true
done < <(aws ec2 describe-addresses \
  --region "$AWS_REGION" \
  --query 'Addresses[?AssociationId==null].[AllocationId, Tags[?Key==`Name`].Value | [0]]' \
  --output text 2>/dev/null)

echo ""
echo "--- Secrets Manager (Kong-era + migrated postgres secrets) ---"
LEGACY_SECRETS=(
  "${NAME_PREFIX}/kong-admin-credentials"
  "${NAME_PREFIX}/postgres-credentials"
  "${NAME_PREFIX}/postgres-connection"
)

for secret_id in "${LEGACY_SECRETS[@]}"; do
  if aws secretsmanager describe-secret \
    --region "$AWS_REGION" \
    --secret-id "$secret_id" &>/dev/null; then
    echo "Deleting secret ${secret_id}..."
    aws secretsmanager delete-secret \
      --region "$AWS_REGION" \
      --secret-id "$secret_id" \
      --force-delete-without-recovery || true
  else
    echo "Secret ${secret_id}: not found"
  fi
done

echo ""
echo "=== Legacy cleanup complete ==="
echo "Run terraform apply to ensure vpc_rds uses SSM Parameter Store (no Secrets Manager)."
