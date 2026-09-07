#!/usr/bin/env bash
# Upload nginx + deploy scripts to EC2 and run deploy-api (idempotent).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODULE_DIR="$ROOT/infra/terraform/modules/data_plane"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

INSTANCE_ID="$(terraform output -raw app_instance_id)"
API_HOSTNAME="$(terraform output -raw api_public_hostname 2>/dev/null || echo api.get1agent.com)"
API_PORT="8000"

SETUP_B64="$(base64 < "$MODULE_DIR/setup-nginx.sh" | tr -d '\n')"
DEPLOY_B64="$(bash "$ROOT/infra/aws/render-deploy-api.sh" | base64 | tr -d '\n')"

PARAMS_FILE="$(mktemp)"
cat >"$PARAMS_FILE" <<EOF
{
  "commands": [
    "set -euo pipefail",
    "mkdir -p /opt/get1agent",
    "echo '${SETUP_B64}' | base64 -d > /opt/get1agent/setup-nginx.sh",
    "chmod +x /opt/get1agent/setup-nginx.sh",
    "echo '${DEPLOY_B64}' | base64 -d > /opt/get1agent/deploy-api.sh",
    "chmod +x /opt/get1agent/deploy-api.sh",
    "export API_HOSTNAME='${API_HOSTNAME}' API_PORT='${API_PORT}'",
    "/opt/get1agent/deploy-api.sh"
  ]
}
EOF

COMMAND_ID="$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "Sync EC2 scripts and deploy get1agent API" \
  --parameters "file://${PARAMS_FILE}" \
  --query Command.CommandId \
  --output text)"

rm -f "$PARAMS_FILE"

aws ssm wait command-executed --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" --region "$AWS_REGION"

aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query StandardOutputContent \
  --output text

STATUS="$(aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query Status \
  --output text)"

if [[ "$STATUS" != "Success" ]]; then
  aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$AWS_REGION" \
    --query StandardErrorContent \
    --output text >&2
  exit 1
fi
