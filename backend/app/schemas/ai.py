from pydantic import BaseModel, Field


class PingRequest(BaseModel):
    message: str = Field(default="你好，请回复 pong", max_length=200)


class PingResponse(BaseModel):
    reply: str
    provider: str
    model: str
    latency_ms: int
