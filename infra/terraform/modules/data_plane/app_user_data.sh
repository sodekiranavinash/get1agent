#!/bin/bash
set -euo pipefail

REGION="${aws_region}"
KONG_IMAGE="${kong_image}"
API_HOSTNAME="${api_hostname}"
KONG_UI_HOSTNAME="${kong_ui_hostname}"
NAME_PREFIX="${name_prefix}"
DB_CREDENTIALS_SECRET_ARN="${db_credentials_secret_arn}"
KONG_ADMIN_SECRET_ARN="${kong_admin_secret_arn}"
DB_HOST="${db_host}"
DB_NAME="${db_name}"
DB_MASTER_USER="${db_master_username}"
DB_IAM_USER="${db_iam_username}"
KONG_DB_NAME="${kong_db_name}"
KONG_IAM_USER="${kong_db_iam_username}"

dnf update -y
dnf install -y docker jq postgresql16 curl
systemctl enable --now docker
usermod -aG docker ec2-user

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
sed -i "s|__KONG_DB_NAME__|$KONG_DB_NAME|g" /opt/get1agent/bootstrap-db.sh
sed -i "s|__KONG_IAM_USER__|$KONG_IAM_USER|g" /opt/get1agent/bootstrap-db.sh
chmod +x /opt/get1agent/bootstrap-db.sh

cat >/opt/get1agent/bootstrap-kong-admin.sh <<'BOOTSTRAP_ADMIN'
${bootstrap_kong_admin_script}
BOOTSTRAP_ADMIN

sed -i "s|__REGION__|$REGION|g" /opt/get1agent/bootstrap-kong-admin.sh
sed -i "s|__KONG_ADMIN_SECRET_ARN__|$KONG_ADMIN_SECRET_ARN|g" /opt/get1agent/bootstrap-kong-admin.sh
sed -i "s|__KONG_UI_HOSTNAME__|$KONG_UI_HOSTNAME|g" /opt/get1agent/bootstrap-kong-admin.sh
chmod +x /opt/get1agent/bootstrap-kong-admin.sh

cat >/opt/get1agent/deploy-kong.sh <<'DEPLOY'
${deploy_kong_script}
DEPLOY

sed -i "s|__REGION__|$REGION|g" /opt/get1agent/deploy-kong.sh
sed -i "s|__KONG_IMAGE__|$KONG_IMAGE|g" /opt/get1agent/deploy-kong.sh
sed -i "s|__DB_HOST__|$DB_HOST|g" /opt/get1agent/deploy-kong.sh
sed -i "s|__KONG_DB_NAME__|$KONG_DB_NAME|g" /opt/get1agent/deploy-kong.sh
sed -i "s|__KONG_IAM_USER__|$KONG_IAM_USER|g" /opt/get1agent/deploy-kong.sh
sed -i "s|__API_HOSTNAME__|$API_HOSTNAME|g" /opt/get1agent/deploy-kong.sh
sed -i "s|__KONG_UI_HOSTNAME__|$KONG_UI_HOSTNAME|g" /opt/get1agent/deploy-kong.sh
chmod +x /opt/get1agent/deploy-kong.sh

cat >/etc/systemd/system/get1agent-kong.service <<UNIT
[Unit]
Description=Kong API Gateway
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/get1agent/deploy-kong.sh
ExecStop=/usr/bin/docker rm -f get1agent-kong

[Install]
WantedBy=multi-user.target
UNIT

# Refresh RDS IAM token every 10 minutes (tokens expire after 15 min)
cat >/etc/systemd/system/get1agent-kong-refresh.service <<REFRESH
[Unit]
Description=Refresh Kong RDS IAM auth token
After=docker.service

[Service]
Type=oneshot
ExecStart=/opt/get1agent/deploy-kong.sh
REFRESH

cat >/etc/systemd/system/get1agent-kong-refresh.timer <<TIMER
[Unit]
Description=Refresh Kong RDS IAM token periodically

[Timer]
OnBootSec=10min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now get1agent-kong.service
systemctl enable --now get1agent-kong-refresh.timer

echo "Kong server bootstrap complete for $NAME_PREFIX"
