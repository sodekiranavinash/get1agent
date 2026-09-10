import json
import os

from sqlalchemy import text

from shared.db.engine import run_async
from shared.db.session import get_session


def _json(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


async def _check_db() -> str:
    database = os.environ["DB_NAME"]
    async with get_session() as session:
        await session.execute(text("SELECT 1"))
    return database


def lambda_handler(_event, _context):
    try:
        database = run_async(_check_db())
        return _json(200, {"status": "ok", "database": database})
    except Exception as exc:
        message = str(exc)
        print(f"health-check db error: {message}")
        return _json(503, {"status": "error", "message": message})
