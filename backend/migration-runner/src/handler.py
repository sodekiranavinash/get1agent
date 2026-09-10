import asyncio
import json
import os
from typing import Any

import asyncpg
import boto3
from alembic import command
from alembic.config import Config

_HERE = os.path.dirname(os.path.abspath(__file__))
_SUPPORTED = {"upgrade", "downgrade", "stamp", "bootstrap"}


def _json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _config() -> Config:
    config_dir = os.environ.get("ALEMBIC_CONFIG_DIR", _HERE)
    config = Config(os.path.join(config_dir, "alembic.ini"))
    config.set_main_option("script_location", config_dir)
    return config


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


async def _load_master_credentials(event: dict[str, Any]) -> dict[str, Any]:
    provided = event.get("masterCredentials")
    if provided:
        return provided

    region = os.environ["AWS_REGION"]
    param_name = os.environ["DB_MASTER_PARAM"]
    ssm = boto3.client("ssm", region_name=region)
    raw = ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]
    return json.loads(raw)


async def _bootstrap(event: dict[str, Any]) -> None:
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    database = os.environ["DB_NAME"]
    iam_user = os.environ["DB_IAM_USER"]

    creds = await _load_master_credentials(event)

    quoted_user = _quote_ident(iam_user)
    quoted_db = _quote_ident(database)
    literal_user = iam_user.replace("'", "''")

    statements = [
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{literal_user}') THEN
            CREATE ROLE {quoted_user} LOGIN;
          END IF;
        END
        $$;
        """,
        f"GRANT rds_iam TO {quoted_user};",
        f"GRANT CONNECT ON DATABASE {quoted_db} TO {quoted_user};",
        f"GRANT USAGE ON SCHEMA public TO {quoted_user};",
        f"GRANT CREATE ON SCHEMA public TO {quoted_user};",
    ]

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=creds["username"],
        password=creds["password"],
        database=creds.get("dbname", database),
        ssl="require",
    )
    try:
        for statement in statements:
            await conn.execute(statement)
    finally:
        await conn.close()


def lambda_handler(event: dict[str, Any] | None, _context) -> dict[str, Any]:
    event = event or {}
    action = str(event.get("action", "upgrade")).lower()
    revision = str(event.get("revision", "head"))

    if action not in _SUPPORTED:
        return _json(400, {"error": f"Unsupported action: {action}", "supported": sorted(_SUPPORTED)})

    try:
        if action == "bootstrap":
            asyncio.run(_bootstrap(event))
            return _json(200, {"status": "ok", "action": action})

        config = _config()
        if action == "upgrade":
            command.upgrade(config, revision)
        elif action == "downgrade":
            command.downgrade(config, revision)
        else:
            command.stamp(config, revision)
    except Exception as exc:
        print(f"migration error: {exc}")
        return _json(500, {"status": "error", "action": action, "revision": revision, "message": str(exc)})

    return _json(200, {"status": "ok", "action": action, "revision": revision})
