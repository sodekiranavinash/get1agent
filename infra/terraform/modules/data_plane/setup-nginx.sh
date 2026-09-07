#!/bin/bash
# Reverse proxy for api.get1agent.com: HTTP :80 -> FastAPI on localhost.
set -euo pipefail

API_HOSTNAME="${API_HOSTNAME:-api.get1agent.com}"
API_PORT="${API_PORT:-8000}"

dnf install -y nginx

cat >/etc/nginx/conf.d/get1agent-api.conf <<NGINX
server {
    listen 80 default_server;
    server_name ${API_HOSTNAME};

    location / {
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX

rm -f /etc/nginx/conf.d/default.conf
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "nginx listening on :80 -> 127.0.0.1:${API_PORT} (${API_HOSTNAME})"
