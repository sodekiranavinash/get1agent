from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("", response_model=MessageResponse)
async def list_tools() -> MessageResponse:
    return MessageResponse(message="List tools — not implemented yet")
