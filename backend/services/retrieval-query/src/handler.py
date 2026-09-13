from __future__ import annotations

import sys
import traceback
from typing import Any

from shared.db.engine import run_async
from shared.db.session import get_session
from shared.retrieval import RetrievalError, execute_retrieval_query


async def _run(payload: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        result = await execute_retrieval_query(session, payload)
        await session.commit()
        return result


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    payload = event if isinstance(event, dict) else {}
    try:
        return run_async(_run(payload))
    except RetrievalError as exc:
        return {"error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # noqa: BLE001
        print(f"retrieval-query error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return {"error": {"code": "internal_error", "message": "Request failed"}}
