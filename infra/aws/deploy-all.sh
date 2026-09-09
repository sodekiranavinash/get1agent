#!/usr/bin/env bash
# Full first-time deploy: infra + Kong gateway.
#
# Usage:
#   bash infra/aws/deploy-all.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

bash "$ROOT/infra/aws/deploy-infra.sh" apply
bash "$ROOT/infra/aws/deploy-kong.sh"
