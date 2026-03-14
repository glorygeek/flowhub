from typing import Any, Literal

from pydantic import BaseModel, Field


class AIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class AIChatRequest(BaseModel):
    messages: list[AIChatMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)


class AIChatResponse(BaseModel):
    enabled: bool
    model: str
    content: str
    provider: str = "openai-compatible"
    reasoning_content: str | None = None
    usage: dict[str, Any] | None = None
