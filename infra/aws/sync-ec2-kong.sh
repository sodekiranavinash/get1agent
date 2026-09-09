#!/usr/bin/env bash
# Upload Kong deploy scripts to EC2 and restart Kong via SSM.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

INSTANCE_ID="$(terraform output -raw app_instance_id)"

# shellcheck source=/dev/null
source "$ROOT/infra/aws/render-kong-scripts.sh"

PARAMS_FILE="$(mktemp)"
trap 'rm -f "$PARAMS_FILE"' EXIT

jq -n \
  --arg deploy_b64 "$(printf '%s' "$RENDER_DEPLOY_SCRIPT" | base64 | tr -d '\n')" \
  --arg bootstrap_db_b64 "$(printf '%s' "$RENDER_BOOTSTRAP_DB_SCRIPT" | base64 | tr -d '\n')" \
  --arg bootstrap_admin_b64 "$(printf '%s' "$RENDER_BOOTSTRAP_ADMIN_SCRIPT" | base64 | tr -d '\n')" \
  '{
    commands: [
      "mkdir -p /opt/get1agent",
      ("echo " + $deploy_b64 + " | base64 -d > /opt/get1agent/deploy-kong.sh"),
      "chmod +x /opt/get1agent/deploy-kong.sh",
      ("echo " + $bootstrap_db_b64 + " | base64 -d > /opt/get1agent/bootstrap-db.sh"),
      "chmod +x /opt/get1agent/bootstrap-db.sh",
      ("echo " + $bootstrap_admin_b64 + " | base64 -d > /opt/get1agent/bootstrap-kong-admin.sh"),
      "chmod +x /opt/get1agent/bootstrap-kong-admin.sh",
      "rm -f /opt/get1agent/.kong_admin_bootstrapped",
      "systemctl restart get1agent-kong.service"
    ]
  }' >"$PARAMS_FILE"

CMD_ID="$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters "file://$PARAMS_FILE" \
  --query "Command.CommandId" \
  --output text)"

echo "SSM command: $CMD_ID"
aws ssm wait command-executed \
  --region "$AWS_REGION" \
  --command-id "$CMD_ID" \
  --instance-id "$INSTANCE_ID"

STATUS="$(aws ssm get-command-invocation \
  --region "$AWS_REGION" \
  --command-id "$CMD_ID" \
  --instance-id "$INSTANCE_ID" \
  --query "Status" \
  --output text)"

if [[ "$STATUS" != "Success" ]]; then
  aws ssm get-command-invocation \
    --region "$AWS_REGION" \
    --command-id "$CMD_ID" \
    --instance-id "$INSTANCE_ID" \
    --query "[Status, StandardOutputContent, StandardErrorContent]" \
    --output text
  echo "SSM deploy failed: $STATUS" >&2
  exit 1
fi

echo "Kong restarted on $INSTANCE_ID"
