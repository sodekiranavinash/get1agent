#!/usr/bin/env bash
# Remove orphaned security group references left by renames/replacements.
# Safe to run before and after terraform apply (idempotent).
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
NAME_PREFIX="${NAME_PREFIX:-get1agent-prod}"

describe_sg() {
  local name="$1"
  aws ec2 describe-security-groups \
    --region "$AWS_REGION" \
    --filters "Name=group-name,Values=${name}" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None"
}

ACTIVE_APP_SG="$(describe_sg "${NAME_PREFIX}-jumpbox")"
LEGACY_APP_SG="$(describe_sg "${NAME_PREFIX}-kong")"
LEGACY_APP_SG2="$(describe_sg "${NAME_PREFIX}-app")"
POSTGRES_SG="$(describe_sg "${NAME_PREFIX}-postgres")"

if [[ "$LEGACY_APP_SG" != "None" && -n "$LEGACY_APP_SG" && "$LEGACY_APP_SG" != "$ACTIVE_APP_SG" ]]; then
  STALE_SG="$LEGACY_APP_SG"
  STALE_NAME="${NAME_PREFIX}-kong"
elif [[ "$LEGACY_APP_SG2" != "None" && -n "$LEGACY_APP_SG2" && "$LEGACY_APP_SG2" != "$ACTIVE_APP_SG" ]]; then
  STALE_SG="$LEGACY_APP_SG2"
  STALE_NAME="${NAME_PREFIX}-app"
else
  echo "No stale security groups to clean"
  exit 0
fi

echo "Stale security group: ${STALE_SG} (${STALE_NAME})"
echo "Active jumpbox SG:    ${ACTIVE_APP_SG}"
echo "Postgres SG:          ${POSTGRES_SG}"

if [[ "$POSTGRES_SG" != "None" && -n "$POSTGRES_SG" ]]; then
  echo "Revoking postgres ingress from stale app SG..."
  aws ec2 revoke-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$POSTGRES_SG" \
    --ip-permissions "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=${STALE_SG}}]" \
    2>/dev/null || true

  mapfile -t RULE_IDS < <(aws ec2 describe-security-group-rules \
    --region "$AWS_REGION" \
    --filters "Name=group-id,Values=${POSTGRES_SG}" \
    --query "SecurityGroupRules[?IsEgress==\`false\` && ReferencedGroupInfo.GroupId==\`${STALE_SG}\`].SecurityGroupRuleId" \
    --output text 2>/dev/null | tr '\t' '\n')

  for rule_id in "${RULE_IDS[@]}"; do
    [[ -z "$rule_id" || "$rule_id" == "None" ]] && continue
    echo "Deleting security group rule ${rule_id}"
    aws ec2 revoke-security-group-ingress \
      --region "$AWS_REGION" \
      --group-id "$POSTGRES_SG" \
      --security-group-rule-ids "$rule_id" \
      2>/dev/null || true
  done
fi

echo "Attempting to delete stale security group ${STALE_SG}..."
if aws ec2 delete-security-group \
  --region "$AWS_REGION" \
  --group-id "$STALE_SG" 2>/dev/null; then
  echo "Deleted stale security group ${STALE_SG}"
else
  echo "Stale security group still in use; Terraform may finish cleanup on the next apply"
fi
