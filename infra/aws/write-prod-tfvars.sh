#!/usr/bin/env bash
# Write prod/terraform.tfvars with all components enabled (desired prod state).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TFVARS="$ROOT/infra/terraform/envs/prod/terraform.tfvars"

# Browser domain allowlist for the AgentCore Browser tool (comma-separated
# suffixes, e.g. "example.com,docs.aws.amazon.com"). Empty denies every domain;
# export BROWSER_ALLOWED_DOMAINS to enable it.
BROWSER_ALLOWED_DOMAINS="${BROWSER_ALLOWED_DOMAINS:-}"

cat >"$TFVARS" <<EOF
aws_region               = "ap-south-1"
enable_api_gateway       = true
enable_backend_lambdas   = true
enable_ingestion         = true
enable_api_custom_domain = true
browser_allowed_domains  = "${BROWSER_ALLOWED_DOMAINS}"
EOF
