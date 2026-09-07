from fastapi import APIRouter

from app.api.v1 import (
    administration,
    agents,
    chat,
    dashboard,
    scheduled_jobs,
    tools,
    user_settings,
    workflows,
)

api_router = APIRouter()
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(
    scheduled_jobs.router,
    prefix="/scheduled-jobs",
    tags=["scheduled-jobs"],
)
api_router.include_router(
    administration.router,
    prefix="/administration",
    tags=["administration"],
)
api_router.include_router(user_settings.router, prefix="/settings", tags=["settings"])
