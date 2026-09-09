#!/usr/bin/env bash
# Upload Kong deploy scripts to EC2 and restart Kong via SSM.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
MODULE_DIR="$ROOT/infra/terraform/modules/data_plane"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

INSTANCE_ID="$(terraform output -raw app_instance_id)"
API_HOSTNAME="$(terraform output -raw api_public_hostname)"
KONG_UI_HOSTNAME="$(terraform output -raw kong_ui_hostname)"
KONG_ADMIN_SECRET_ARN="$(terraform output -raw kong_admin_credentials_secret_arn)"
DB_CREDS_SECRET_ARN="$(terraform output -raw postgres_credentials_secret_arn)"
DB_HOST="$(terraform output -raw postgres_endpoint)"

# Render deploy script with current Terraform outputs
DEPLOY_SCRIPT="$(sed \
  -e "s|__REGION__|${AWS_REGION}|g" \
  -e "s|__KONG_IMAGE__|kong:3.8|g" \
  -e "s|__DB_HOST__|${DB_HOST}|g" \
  -e "s|__KONG_DB_NAME__|kong|g" \
  -e "s|__KONG_IAM_USER__|kong_app|g" \
  -e "s|__API_HOSTNAME__|${API_HOSTNAME}|g" \
  -e "s|__KONG_UI_HOSTNAME__|${KONG_UI_HOSTNAME}|g" \
  "$MODULE_DIR/deploy-kong.sh.tpl")"

BOOTSTRAP_DB="$(sed \
  -e "s|__REGION__|${AWS_REGION}|g" \
  -e "s|__DB_CREDENTIALS_SECRET_ARN__|${DB_CREDS_SECRET_ARN}|g" \
  -e "s|__DB_HOST__|${DB_HOST}|g" \
  -e "s|__DB_NAME__|get1agent|g" \
  -e "s|__DB_MASTER_USER__|get1agent|g" \
  -e "s|__DB_IAM_USER__|get1agent_app|g" \
  -e "s|__KONG_DB_NAME__|kong|g" \
  -e "s|__KONG_IAM_USER__|kong_app|g" \
  "$MODULE_DIR/bootstrap-db.sh")"

BOOTSTRAP_ADMIN="$(sed \
  -e "s|__REGION__|${AWS_REGION}|g" \
  -e "s|__KONG_ADMIN_SECRET_ARN__|${KONG_ADMIN_SECRET_ARN}|g" \
  -e "s|__KONG_UI_HOSTNAME__|${KONG_UI_HOSTNAME}|g" \
  "$MODULE_DIR/bootstrap-kong-admin.sh")"

# Base64-encode scripts for SSM
DEPLOY_B64="$(printf '%s' "$DEPLOY_SCRIPT" | base64)"
BOOTSTRAP_DB_B64="$(printf '%s' "$BOOTSTRAP_DB" | base64)"
BOOTSTRAP_ADMIN_B64="$(printf '%s' "$BOOTSTRAP_ADMIN" | base64)"

CMD_ID="$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[
    \"echo '${DEPLOY_B64}' | base64 -d > /opt/get1agent/deploy-kong.sh && chmod +x /opt/get1agent/deploy-kong.sh\",
    \"echo '${BOOTSTRAP_DB_B64}' | base64 -d > /opt/get1agent/bootstrap-db.sh && chmod +x /opt/get1agent/bootstrap-db.sh\",
    \"echo '${BOOTSTRAP_ADMIN_B64}' | base64 -d > /opt/get1agent/bootstrap-kong-admin.sh && chmod +x /opt/get1agent/bootstrap-kong-admin.sh\",
    \"rm -f /opt/get1agent/.kong_admin_bootstrapped\",
    \"systemctl restart get1agent-kong.service\"
  ]" \
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
