from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("", response_model=MessageResponse)
async def list_agents() -> MessageResponse:
    return MessageResponse(message="List agents — not implemented yet")


@router.post("", response_model=MessageResponse)
async def create_agent() -> MessageResponse:
    return MessageResponse(message="Create agent — not implemented yet")
