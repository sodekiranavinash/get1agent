#!/usr/bin/env bash
# One-time / laptop: create the Terraform state bucket and move bootstrap state onto it.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run-terraform.sh" bootstrap apply
