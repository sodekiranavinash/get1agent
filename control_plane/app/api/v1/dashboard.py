from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("/summary", response_model=MessageResponse)
async def get_summary() -> MessageResponse:
    return MessageResponse(message="Dashboard summary — not implemented yet")
