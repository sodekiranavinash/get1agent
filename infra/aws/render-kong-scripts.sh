#!/usr/bin/env bash
# Render Kong bootstrap/deploy scripts with Terraform outputs.
# Usage: eval "$(bash infra/aws/render-kong-scripts.sh)"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
MODULE_DIR="$ROOT/infra/terraform/modules/data_plane"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

export RENDER_AWS_REGION="$AWS_REGION"
export RENDER_KONG_IMAGE="$(terraform output -raw kong_image)"
export RENDER_DB_HOST="$(terraform output -raw postgres_endpoint)"
export RENDER_DB_NAME="$(terraform output -raw postgres_db_name)"
export RENDER_DB_MASTER_USER="$(terraform output -raw postgres_username)"
export RENDER_DB_IAM_USER="$(terraform output -raw db_iam_username)"
export RENDER_KONG_DB_NAME="$(terraform output -raw kong_db_name)"
export RENDER_KONG_IAM_USER="$(terraform output -raw kong_db_iam_username)"
export RENDER_API_HOSTNAME="$(terraform output -raw api_public_hostname)"
export RENDER_KONG_UI_HOSTNAME="$(terraform output -raw kong_ui_hostname)"
export RENDER_DB_CREDS_SECRET_ARN="$(terraform output -raw postgres_credentials_secret_arn)"
export RENDER_KONG_ADMIN_SECRET_ARN="$(terraform output -raw kong_admin_credentials_secret_arn)"

render_script() {
  local template="$1"
  sed \
    -e "s|__REGION__|${RENDER_AWS_REGION}|g" \
    -e "s|__KONG_IMAGE__|${RENDER_KONG_IMAGE}|g" \
    -e "s|__DB_HOST__|${RENDER_DB_HOST}|g" \
    -e "s|__DB_NAME__|${RENDER_DB_NAME}|g" \
    -e "s|__DB_MASTER_USER__|${RENDER_DB_MASTER_USER}|g" \
    -e "s|__DB_IAM_USER__|${RENDER_DB_IAM_USER}|g" \
    -e "s|__KONG_DB_NAME__|${RENDER_KONG_DB_NAME}|g" \
    -e "s|__KONG_IAM_USER__|${RENDER_KONG_IAM_USER}|g" \
    -e "s|__API_HOSTNAME__|${RENDER_API_HOSTNAME}|g" \
    -e "s|__KONG_UI_HOSTNAME__|${RENDER_KONG_UI_HOSTNAME}|g" \
    -e "s|__DB_CREDENTIALS_SECRET_ARN__|${RENDER_DB_CREDS_SECRET_ARN}|g" \
    -e "s|__KONG_ADMIN_SECRET_ARN__|${RENDER_KONG_ADMIN_SECRET_ARN}|g" \
    "$template"
}

export RENDER_DEPLOY_SCRIPT="$(render_script "$MODULE_DIR/deploy-kong.sh.tpl")"
export RENDER_BOOTSTRAP_DB_SCRIPT="$(render_script "$MODULE_DIR/bootstrap-db.sh")"
export RENDER_BOOTSTRAP_ADMIN_SCRIPT="$(render_script "$MODULE_DIR/bootstrap-kong-admin.sh")"
