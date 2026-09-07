#!/bin/bash
set -euo pipefail

REGION="${aws_region}"
ECR_URL="${ecr_repository_url}"
API_PORT="${api_port}"
NAME_PREFIX="${name_prefix}"
DB_CREDENTIALS_SECRET_ARN="${db_credentials_secret_arn}"
DB_HOST="${db_host}"
DB_NAME="${db_name}"
DB_MASTER_USER="${db_master_username}"
DB_IAM_USER="${db_iam_username}"

dnf update -y
dnf install -y docker jq postgresql16 nginx
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /opt/get1agent
chmod 755 /opt/get1agent

cat >/opt/get1agent/setup-nginx.sh <<'SETUP_NGINX'
${setup_nginx_script}
SETUP_NGINX
chmod +x /opt/get1agent/setup-nginx.sh

cat >/opt/get1agent/bootstrap-db-iam-user.sh <<'BOOTSTRAP'
#!/bin/bash
set -euo pipefail

REGION="__REGION__"
DB_CREDENTIALS_SECRET_ARN="__DB_CREDENTIALS_SECRET_ARN__"
DB_HOST="__DB_HOST__"
DB_NAME="__DB_NAME__"
DB_MASTER_USER="__DB_MASTER_USER__"
DB_IAM_USER="__DB_IAM_USER__"
MARKER="/opt/get1agent/.db_iam_user_bootstrapped"

if [[ -f "$MARKER" ]]; then
  echo "IAM DB user already bootstrapped"
  exit 0
fi

SECRET_JSON="$(aws secretsmanager get-secret-value \
  --region "$REGION" \
  --secret-id "$DB_CREDENTIALS_SECRET_ARN" \
  --query SecretString \
  --output text)"

DB_PASSWORD="$(echo "$SECRET_JSON" | jq -r '.password')"

for attempt in $(seq 1 30); do
  if PGPASSWORD="$DB_PASSWORD" psql \
    "host=$DB_HOST port=5432 dbname=$DB_NAME user=$DB_MASTER_USER sslmode=require" \
    -v ON_ERROR_STOP=1 \
    -c "SELECT 1" >/dev/null 2>&1; then
    break
  fi
  echo "Waiting for RDS ($attempt/30)..."
  sleep 10
done

PGPASSWORD="$DB_PASSWORD" psql \
  "host=$DB_HOST port=5432 dbname=$DB_NAME user=$DB_MASTER_USER sslmode=require" \
  -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '__DB_IAM_USER__') THEN
    CREATE USER __DB_IAM_USER__;
  END IF;
END
\$\$;
GRANT rds_iam TO __DB_IAM_USER__;
GRANT CONNECT ON DATABASE __DB_NAME__ TO __DB_IAM_USER__;
GRANT USAGE, CREATE ON SCHEMA public TO __DB_IAM_USER__;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO __DB_IAM_USER__;
SQL

touch "$MARKER"
echo "Bootstrapped IAM database user __DB_IAM_USER__"
BOOTSTRAP

sed -i "s|__REGION__|$REGION|g" /opt/get1agent/bootstrap-db-iam-user.sh
sed -i "s|__DB_CREDENTIALS_SECRET_ARN__|$DB_CREDENTIALS_SECRET_ARN|g" /opt/get1agent/bootstrap-db-iam-user.sh
sed -i "s|__DB_HOST__|$DB_HOST|g" /opt/get1agent/bootstrap-db-iam-user.sh
sed -i "s|__DB_NAME__|$DB_NAME|g" /opt/get1agent/bootstrap-db-iam-user.sh
sed -i "s|__DB_MASTER_USER__|$DB_MASTER_USER|g" /opt/get1agent/bootstrap-db-iam-user.sh
sed -i "s|__DB_IAM_USER__|$DB_IAM_USER|g" /opt/get1agent/bootstrap-db-iam-user.sh
sed -i "s|__DB_NAME__|$DB_NAME|g" /opt/get1agent/bootstrap-db-iam-user.sh
chmod +x /opt/get1agent/bootstrap-db-iam-user.sh
/opt/get1agent/bootstrap-db-iam-user.sh

cat >/opt/get1agent/deploy-api.sh <<'DEPLOY'
${deploy_api_script}
DEPLOY

sed -i "s|__REGION__|$REGION|g" /opt/get1agent/deploy-api.sh
sed -i "s|__ECR_URL__|$ECR_URL|g" /opt/get1agent/deploy-api.sh
sed -i "s|__API_PORT__|$API_PORT|g" /opt/get1agent/deploy-api.sh
sed -i "s|__DB_HOST__|$DB_HOST|g" /opt/get1agent/deploy-api.sh
sed -i "s|__DB_NAME__|$DB_NAME|g" /opt/get1agent/deploy-api.sh
sed -i "s|__DB_IAM_USER__|$DB_IAM_USER|g" /opt/get1agent/deploy-api.sh
chmod +x /opt/get1agent/deploy-api.sh

export API_HOSTNAME="${api_hostname}"
export API_PORT="${api_port}"
/opt/get1agent/setup-nginx.sh

cat >/etc/systemd/system/get1agent-api.service <<UNIT
[Unit]
Description=get1agent control_plane FastAPI container
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/get1agent/deploy-api.sh
ExecStop=/usr/bin/docker rm -f get1agent-api

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable get1agent-api.service

echo "App server bootstrap complete for $NAME_PREFIX"
