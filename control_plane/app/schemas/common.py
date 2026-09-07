from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    database: str
