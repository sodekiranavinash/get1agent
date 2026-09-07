#!/usr/bin/env bash
# Read/write data_plane_ssh_cidr_blocks in dev terraform.tfvars.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TFVARS="$ROOT/infra/terraform/envs/dev/terraform.tfvars"

normalize_cidr() {
  local value="$1"
  value="$(echo "$value" | tr -d '[:space:]')"
  if [[ "$value" != */* ]]; then
    value="${value}/32"
  fi
  echo "$value"
}

read_ssh_cidrs() {
  if [[ ! -f "$TFVARS" ]]; then
    return 0
  fi
  python3 - "$TFVARS" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text()
match = re.search(r'data_plane_ssh_cidr_blocks\s*=\s*\[(.*?)\]', text, re.S)
if not match:
    sys.exit(0)
inner = match.group(1)
for item in re.findall(r'"([^"]+)"', inner):
    print(item)
PY
}

write_tfvars() {
  local -a cidrs=("$@")
  local cidr_list=""
  for cidr in "${cidrs[@]}"; do
    cidr_list+="\"${cidr}\", "
  done
  cidr_list="[${cidr_list%, }]"

  cat >"$TFVARS" <<EOF
aws_region   = "us-east-1"
package_path = "../../../../tools/challan-extractor/dist/function.zip"
enable_data_plane          = true
data_plane_ssh_cidr_blocks = ${cidr_list}
EOF
}

merge_ssh_cidr() {
  local new_cidr="$1"
  local -a existing=()
  local -a merged=()
  local seen=""

  mapfile -t existing < <(read_ssh_cidrs || true)

  for cidr in "${existing[@]}" "$new_cidr"; do
    [[ -z "$cidr" ]] && continue
    cidr="$(normalize_cidr "$cidr")"
    if [[ "$seen" != *"|$cidr|"* ]]; then
      merged+=("$cidr")
      seen+="|$cidr|"
    fi
  done

  if [[ ${#merged[@]} -eq 0 ]]; then
    echo "No SSH CIDR blocks to write." >&2
    exit 1
  fi

  write_tfvars "${merged[@]}"
  printf '%s\n' "${merged[@]}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  if [[ $# -ne 1 ]]; then
    echo "usage: $0 <ip-or-cidr>" >&2
    exit 2
  fi
  merge_ssh_cidr "$(normalize_cidr "$1")"
fi
