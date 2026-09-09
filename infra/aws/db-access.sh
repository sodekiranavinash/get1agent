#!/usr/bin/env bash
# On-demand RDS access: start jumpbox (gets public IPv4), SSM tunnel, stop on exit.
#
# IPv4 is billed only while the instance is running (~$0.005/hr). Stopping releases it.
#
# Usage:
#   bash infra/aws/db-access.sh              # tunnel on localhost:15432 (stops EC2 when you exit)
#   bash infra/aws/db-access.sh --show-creds   # print DBeaver credentials (no EC2 start)
#   bash infra/aws/db-access.sh --stop        # stop jumpbox now (release public IPv4)
#   bash infra/aws/db-access.sh --keep-running # don't stop EC2 when tunnel exits
#
# DBeaver: host localhost, port 15432, SSH tab OFF, SSL require
#
# Requires: AWS CLI, Session Manager plugin (brew install --cask session-manager-plugin)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/prod"
AWS_REGION="${AWS_REGION:-us-east-1}"
LOCAL_PORT="${LOCAL_PORT:-15432}"
MODE="tunnel"
KEEP_RUNNING=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --show-creds) MODE="creds"; shift ;;
    --stop) MODE="stop"; shift ;;
    --keep-running) KEEP_RUNNING=1; shift ;;
    --port)
      LOCAL_PORT="$2"
      shift 2
      ;;
    -h | --help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

cd "$ENV_DIR"

if ! terraform output -raw jumpbox_instance_id &>/dev/null; then
  echo "VPC/RDS stack not found. Run: bash infra/aws/deploy-infra.sh apply" >&2
  exit 1
fi

INSTANCE_ID="$(terraform output -raw jumpbox_instance_id)"
RDS_HOST="$(terraform output -raw postgres_endpoint)"
CONN_PARAM="$(terraform output -raw postgres_connection_parameter_name)"

instance_state() {
  aws ec2 describe-instances \
    --region "$AWS_REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].State.Name' \
    --output text
}

wait_for_running() {
  echo "Waiting for EC2 to reach running state..."
  aws ec2 wait instance-running \
    --region "$AWS_REGION" \
    --instance-ids "$INSTANCE_ID"
}

wait_for_ssm() {
  echo "Waiting for SSM agent (up to 3 min)..."
  for _ in $(seq 1 36); do
    status="$(aws ssm describe-instance-information \
      --region "$AWS_REGION" \
      --filters "Key=InstanceIds,Values=${INSTANCE_ID}" \
      --query 'InstanceInformationList[0].PingStatus' \
      --output text 2>/dev/null || echo "None")"
    if [[ "$status" == "Online" ]]; then
      echo "SSM agent online."
      return 0
    fi
    sleep 5
  done
  echo "SSM agent did not come online. Try again in a minute." >&2
  exit 1
}

stop_instance() {
  local state
  state="$(instance_state)"
  if [[ "$state" == "running" || "$state" == "pending" ]]; then
    echo "Stopping jumpbox ${INSTANCE_ID} (public IPv4 will be released)..."
    aws ec2 stop-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" >/dev/null
  fi
}

if [[ "$MODE" == "creds" ]]; then
  aws ssm get-parameter \
    --region "$AWS_REGION" \
    --name "$CONN_PARAM" \
    --with-decryption \
    --query Parameter.Value \
    --output text | python3 -m json.tool
  exit 0
fi

if [[ "$MODE" == "stop" ]]; then
  stop_instance
  echo "Jumpbox stop requested."
  exit 0
fi

STARTED_BY_SCRIPT=0
STATE="$(instance_state)"

if [[ "$STATE" == "stopped" ]]; then
  echo "Starting jumpbox ${INSTANCE_ID} (public IPv4 assigned while running)..."
  aws ec2 start-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" >/dev/null
  STARTED_BY_SCRIPT=1
  wait_for_running
  wait_for_ssm
elif [[ "$STATE" == "running" ]]; then
  wait_for_ssm
else
  echo "Instance is ${STATE}; wait and retry." >&2
  exit 1
fi

cleanup() {
  if [[ "$KEEP_RUNNING" -eq 0 ]]; then
    stop_instance
  else
    echo "Leaving jumpbox running (--keep-running)."
  fi
}
trap cleanup EXIT

echo ""
echo "RDS host: $RDS_HOST"
echo "Local port: $LOCAL_PORT"
echo "Credentials: bash infra/aws/db-access.sh --show-creds"
echo ""
echo "DBeaver: host localhost, port $LOCAL_PORT, SSH tab OFF"
echo "Press Ctrl+C to close tunnel and stop jumpbox (releases public IPv4)."
echo ""
exec aws ssm start-session \
  --region "$AWS_REGION" \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"${RDS_HOST}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"${LOCAL_PORT}\"]}"
