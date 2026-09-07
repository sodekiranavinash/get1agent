from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("/usage", response_model=MessageResponse)
async def get_usage() -> MessageResponse:
    return MessageResponse(message="Token usage — not implemented yet")


@router.get("/api-keys", response_model=MessageResponse)
async def list_api_keys() -> MessageResponse:
    return MessageResponse(message="API keys — not implemented yet")
