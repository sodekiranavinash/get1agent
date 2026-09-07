from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("", response_model=MessageResponse)
async def list_workflows() -> MessageResponse:
    return MessageResponse(message="List workflows — not implemented yet")


@router.post("", response_model=MessageResponse)
async def create_workflow() -> MessageResponse:
    return MessageResponse(message="Create workflow — not implemented yet")
