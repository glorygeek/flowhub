from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.schemas.ai import AIChatRequest, AIChatResponse
from app.services.ai_gateway import can_use_ai, request_ai_chat

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat", response_model=AIChatResponse)
def chat_with_ai(payload: AIChatRequest):
    settings = get_settings()
    if not can_use_ai(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI gateway is not configured",
        )

    result = request_ai_chat(
        settings=settings,
        messages=[message.model_dump(mode="json") for message in payload.messages],
        model=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI gateway request failed",
        )

    usage = result.raw_response.get("usage") if isinstance(result.raw_response, dict) else None
    return AIChatResponse(
        enabled=True,
        model=result.model,
        content=result.content,
        provider=result.provider,
        reasoning_content=result.reasoning_content,
        usage=usage if isinstance(usage, dict) else None,
    )
