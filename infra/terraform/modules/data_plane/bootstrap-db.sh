#!/bin/bash
# Bootstrap PostgreSQL: app IAM user + kong database + kong IAM user.
set -euo pipefail

REGION="__REGION__"
DB_CREDENTIALS_SECRET_ARN="__DB_CREDENTIALS_SECRET_ARN__"
DB_HOST="__DB_HOST__"
DB_NAME="__DB_NAME__"
DB_MASTER_USER="__DB_MASTER_USER__"
DB_IAM_USER="__DB_IAM_USER__"
KONG_DB="__KONG_DB_NAME__"
KONG_IAM_USER="__KONG_IAM_USER__"
MARKER="/opt/get1agent/.db_bootstrapped"

if [[ -f "$MARKER" ]]; then
  echo "Database already bootstrapped"
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

# App IAM user (for future serverless services on get1agent DB)
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

# Kong database
if ! PGPASSWORD="$DB_PASSWORD" psql \
  "host=$DB_HOST port=5432 dbname=$DB_NAME user=$DB_MASTER_USER sslmode=require" \
  -tAc "SELECT 1 FROM pg_database WHERE datname='__KONG_DB_NAME__'" | grep -q 1; then
  PGPASSWORD="$DB_PASSWORD" psql \
    "host=$DB_HOST port=5432 dbname=$DB_NAME user=$DB_MASTER_USER sslmode=require" \
    -v ON_ERROR_STOP=1 \
    -c "CREATE DATABASE __KONG_DB_NAME__"
fi

# Kong IAM user
PGPASSWORD="$DB_PASSWORD" psql \
  "host=$DB_HOST port=5432 dbname=$KONG_DB user=$DB_MASTER_USER sslmode=require" \
  -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '__KONG_IAM_USER__') THEN
    CREATE USER __KONG_IAM_USER__;
  END IF;
END
\$\$;
GRANT rds_iam TO __KONG_IAM_USER__;
GRANT CONNECT ON DATABASE __KONG_DB_NAME__ TO __KONG_IAM_USER__;
GRANT ALL ON SCHEMA public TO __KONG_IAM_USER__;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO __KONG_IAM_USER__;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO __KONG_IAM_USER__;
SQL

touch "$MARKER"
echo "Bootstrapped databases: __DB_NAME__ (__DB_IAM_USER__) and __KONG_DB_NAME__ (__KONG_IAM_USER__)"
