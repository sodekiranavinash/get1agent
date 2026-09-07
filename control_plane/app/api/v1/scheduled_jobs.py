from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("", response_model=MessageResponse)
async def list_scheduled_jobs() -> MessageResponse:
    return MessageResponse(message="List scheduled jobs — not implemented yet")
