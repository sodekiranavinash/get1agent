from fastapi import APIRouter

from app.schemas.common import HealthResponse, ReadyResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from app.config import get_settings

    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="control_plane",
        version=settings.app_version,
    )


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    from app.core.database import check_database_connection

    try:
        await check_database_connection()
        db_status = "ok"
        status = "ready"
    except Exception:
        db_status = "unavailable"
        status = "degraded"

    return ReadyResponse(status=status, database=db_status)
