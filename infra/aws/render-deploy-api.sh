#!/usr/bin/env bash
# Render deploy-api.sh with Terraform outputs (for SSM sync to existing EC2).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
TEMPLATE="$ROOT/infra/terraform/modules/data_plane/deploy-api.sh.tpl"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

rendered="$(<"$TEMPLATE")"
rendered="${rendered//__REGION__/$AWS_REGION}"
rendered="${rendered//__ECR_URL__/$(terraform output -raw ecr_repository_url)}"
rendered="${rendered//__API_PORT__/8000}"
rendered="${rendered//__DB_HOST__/$(terraform output -raw postgres_endpoint)}"
rendered="${rendered//__DB_NAME__/get1agent}"
rendered="${rendered//__DB_IAM_USER__/get1agent_app}"

printf '%s' "$rendered"
