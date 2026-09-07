from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.post("/sessions", response_model=MessageResponse)
async def create_chat_session() -> MessageResponse:
    return MessageResponse(message="Chat session — not implemented yet")
