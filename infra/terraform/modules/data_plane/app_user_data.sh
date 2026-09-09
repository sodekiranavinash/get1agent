#!/bin/bash
# SSM jumpbox for RDS tunneling only (no Kong, no Docker).
set -euo pipefail

REGION="${aws_region}"
DB_CREDENTIALS_SECRET_ARN="${db_credentials_secret_arn}"
DB_HOST="${db_host}"
DB_NAME="${db_name}"
DB_MASTER_USER="${db_master_username}"
DB_IAM_USER="${db_iam_username}"

dnf install -y jq postgresql16
mkdir -p /opt/get1agent
chmod 755 /opt/get1agent

cat >/opt/get1agent/bootstrap-db.sh <<'BOOTSTRAP_DB'
${bootstrap_db_script}
BOOTSTRAP_DB

sed -i "s|__REGION__|$REGION|g" /opt/get1agent/bootstrap-db.sh
sed -i "s|__DB_CREDENTIALS_SECRET_ARN__|$DB_CREDENTIALS_SECRET_ARN|g" /opt/get1agent/bootstrap-db.sh
sed -i "s|__DB_HOST__|$DB_HOST|g" /opt/get1agent/bootstrap-db.sh
sed -i "s|__DB_NAME__|$DB_NAME|g" /opt/get1agent/bootstrap-db.sh
sed -i "s|__DB_MASTER_USER__|$DB_MASTER_USER|g" /opt/get1agent/bootstrap-db.sh
sed -i "s|__DB_IAM_USER__|$DB_IAM_USER|g" /opt/get1agent/bootstrap-db.sh
chmod +x /opt/get1agent/bootstrap-db.sh
/opt/get1agent/bootstrap-db.sh

echo "Jumpbox bootstrap complete"
