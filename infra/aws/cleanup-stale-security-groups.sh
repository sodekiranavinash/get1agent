#!/usr/bin/env bash
# Remove orphaned security group references left by renames/replacements.
# Safe to run before and after terraform apply (idempotent).
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
NAME_PREFIX="${NAME_PREFIX:-get1agent-dev}"

describe_sg() {
  local name="$1"
  aws ec2 describe-security-groups \
    --region "$AWS_REGION" \
    --filters "Name=group-name,Values=${name}" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None"
}

ACTIVE_APP_SG="$(describe_sg "${NAME_PREFIX}-kong")"
LEGACY_APP_SG="$(describe_sg "${NAME_PREFIX}-app")"
POSTGRES_SG="$(describe_sg "${NAME_PREFIX}-postgres")"

if [[ "$LEGACY_APP_SG" == "None" || -z "$LEGACY_APP_SG" ]]; then
  echo "No stale ${NAME_PREFIX}-app security group"
  exit 0
fi

if [[ "$LEGACY_APP_SG" == "$ACTIVE_APP_SG" ]]; then
  echo "Legacy and active app security groups are the same; nothing to clean"
  exit 0
fi

echo "Stale security group: ${LEGACY_APP_SG} (${NAME_PREFIX}-app)"
echo "Active Kong SG:       ${ACTIVE_APP_SG}"
echo "Postgres SG:          ${POSTGRES_SG}"

if [[ "$POSTGRES_SG" != "None" && -n "$POSTGRES_SG" ]]; then
  echo "Revoking postgres ingress from stale app SG..."
  aws ec2 revoke-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$POSTGRES_SG" \
    --ip-permissions "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=${LEGACY_APP_SG}}]" \
    2>/dev/null || true

  mapfile -t RULE_IDS < <(aws ec2 describe-security-group-rules \
    --region "$AWS_REGION" \
    --filters "Name=group-id,Values=${POSTGRES_SG}" \
    --query "SecurityGroupRules[?IsEgress==\`false\` && ReferencedGroupInfo.GroupId==\`${LEGACY_APP_SG}\`].SecurityGroupRuleId" \
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

echo "Attempting to delete stale security group ${LEGACY_APP_SG}..."
if aws ec2 delete-security-group \
  --region "$AWS_REGION" \
  --group-id "$LEGACY_APP_SG" 2>/dev/null; then
  echo "Deleted stale security group ${LEGACY_APP_SG}"
else
  echo "Stale security group still in use; Terraform may finish cleanup on the next apply"
fi
