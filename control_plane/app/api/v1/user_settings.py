from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("", response_model=MessageResponse)
async def get_settings() -> MessageResponse:
    return MessageResponse(message="User settings — not implemented yet")
