#!/usr/bin/env bash
# Write prod/terraform.tfvars with all components enabled (desired prod state).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TFVARS="$ROOT/infra/terraform/envs/prod/terraform.tfvars"

cat >"$TFVARS" <<'EOF'
aws_region               = "ap-south-1"
enable_api_gateway       = true
enable_backend_lambdas   = true
enable_ingestion         = true
enable_api_custom_domain = true
EOF
