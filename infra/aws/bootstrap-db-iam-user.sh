#!/usr/bin/env bash
# Create the PostgreSQL IAM user for Lambda RDS auth (idempotent).
# Runs on the jumpbox via SSM; safe to re-run after RDS apply.
#
# Usage:
#   bash infra/aws/bootstrap-db-iam-user.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/prod"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

if ! terraform output -raw postgres_endpoint &>/dev/null; then
  echo "RDS not deployed; skipping IAM user bootstrap."
  exit 0
fi

INSTANCE_ID="$(terraform output -raw jumpbox_instance_id)"
RDS_HOST="$(terraform output -raw postgres_endpoint)"
DB_NAME="$(terraform output -raw postgres_db_name)"
IAM_USER="$(terraform output -raw db_iam_username)"
CREDS_PARAM="$(terraform output -raw postgres_credentials_parameter_name)"

instance_state() {
  aws ec2 describe-instances \
    --region "$AWS_REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].State.Name' \
    --output text
}

wait_for_running() {
  aws ec2 wait instance-running \
    --region "$AWS_REGION" \
    --instance-ids "$INSTANCE_ID"
}

wait_for_ssm() {
  for _ in $(seq 1 36); do
    status="$(aws ssm describe-instance-information \
      --region "$AWS_REGION" \
      --filters "Key=InstanceIds,Values=${INSTANCE_ID}" \
      --query 'InstanceInformationList[0].PingStatus' \
      --output text 2>/dev/null || echo "None")"
    if [[ "$status" == "Online" ]]; then
      return 0
    fi
    sleep 5
  done
  echo "SSM agent did not come online on ${INSTANCE_ID}." >&2
  exit 1
}

STARTED_BY_SCRIPT=0
STATE="$(instance_state)"
if [[ "$STATE" == "stopped" ]]; then
  echo "Starting jumpbox ${INSTANCE_ID} for DB IAM bootstrap..."
  aws ec2 start-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" >/dev/null
  STARTED_BY_SCRIPT=1
  wait_for_running
elif [[ "$STATE" != "running" ]]; then
  echo "Jumpbox is ${STATE}; cannot bootstrap DB IAM user." >&2
  exit 1
fi

wait_for_ssm

REMOTE_SCRIPT="$(cat <<EOF
set -euo pipefail
MARKER="/opt/get1agent/.db_iam_bootstrapped"
if [[ -f "\$MARKER" ]]; then
  echo "IAM DB user already bootstrapped"
  exit 0
fi

if ! command -v psql >/dev/null 2>&1; then
  sudo dnf install -y postgresql15
fi

CREDS_JSON="\$(aws ssm get-parameter \\
  --region ${AWS_REGION} \\
  --name ${CREDS_PARAM} \\
  --with-decryption \\
  --query Parameter.Value \\
  --output text)"

eval "\$(CREDS_JSON="\$CREDS_JSON" python3 - <<'PY'
import json, os, shlex
c = json.loads(os.environ["CREDS_JSON"])
print(f"export PGHOST={shlex.quote('${RDS_HOST}')}")
print(f"export PGPORT=5432")
print(f"export PGDATABASE={shlex.quote(c['dbname'])}")
print(f"export PGUSER={shlex.quote(c['username'])}")
print(f"export PGPASSWORD={shlex.quote(c['password'])}")
PY
)"

export PGSSLMODE=require
psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  CREATE USER ${IAM_USER};
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
\$\$;
GRANT rds_iam TO ${IAM_USER};
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${IAM_USER};
SQL

sudo mkdir -p /opt/get1agent
sudo touch "\$MARKER"
echo "Bootstrapped IAM DB user ${IAM_USER}"
EOF
)"

COMMAND_ID="$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters "$(python3 -c 'import json,sys; print(json.dumps({"commands": [sys.stdin.read()]}))' <<<"$REMOTE_SCRIPT")" \
  --query Command.CommandId \
  --output text)"

echo "Waiting for DB IAM bootstrap command ${COMMAND_ID}..."
bootstrap_status="Pending"
for _ in $(seq 1 60); do
  bootstrap_status="$(aws ssm get-command-invocation \
    --region "$AWS_REGION" \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --query Status \
    --output text 2>/dev/null || echo "Pending")"
  case "$bootstrap_status" in
    Success)
      aws ssm get-command-invocation \
        --region "$AWS_REGION" \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --query StandardOutputContent \
        --output text
      break
      ;;
    Failed | Cancelled | TimedOut)
      aws ssm get-command-invocation \
        --region "$AWS_REGION" \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --query '[StandardOutputContent, StandardErrorContent]' \
        --output text >&2
      exit 1
      ;;
    *)
      sleep 5
      ;;
  esac
done

if [[ "$bootstrap_status" != "Success" ]]; then
  echo "DB IAM bootstrap timed out." >&2
  exit 1
fi

if [[ "$STARTED_BY_SCRIPT" -eq 1 ]]; then
  echo "Stopping jumpbox ${INSTANCE_ID}..."
  aws ec2 stop-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" >/dev/null
fi

echo "DB IAM user bootstrap complete."
