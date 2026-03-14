import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AIChatResult:
    provider: str
    model: str
    content: str
    reasoning_content: str | None
    raw_response: dict[str, Any]


@dataclass
class AIRuntimeConfig:
    enabled: bool
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    default_temperature: float
    thinking_enabled: bool


def resolve_ai_runtime(settings: Settings) -> AIRuntimeConfig:
    enabled = settings.ai_enabled or settings.planner_ai_enabled
    base_url = (settings.ai_base_url or settings.planner_ai_base_url).strip()
    model = (settings.ai_model or settings.planner_ai_model).strip()
    api_key = (settings.ai_api_key or settings.planner_ai_api_key).strip()
    timeout_seconds = settings.ai_timeout_seconds or settings.planner_ai_timeout_seconds
    default_temperature = settings.ai_default_temperature
    return AIRuntimeConfig(
        enabled=enabled,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        default_temperature=default_temperature,
        thinking_enabled=settings.ai_thinking_enabled,
    )


def can_use_ai(settings: Settings) -> bool:
    runtime = resolve_ai_runtime(settings)
    return bool(runtime.enabled and runtime.base_url and runtime.model and runtime.api_key)


def detect_provider(runtime: AIRuntimeConfig) -> str:
    base_url = runtime.base_url.lower()
    model = runtime.model.lower()
    if "deepseek.com" in base_url or model.startswith("deepseek-"):
        return "deepseek"
    return "openai-compatible"


def build_chat_payload(
    *,
    runtime: AIRuntimeConfig,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    selected_model = model or runtime.model
    payload: dict[str, Any] = {
        "model": selected_model,
        "temperature": temperature if temperature is not None else runtime.default_temperature,
        "messages": messages,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    provider = detect_provider(runtime)
    if (
        provider == "deepseek"
        and runtime.thinking_enabled
        and str(selected_model).strip().lower() == "deepseek-chat"
    ):
        payload["thinking"] = {"type": "enabled"}

    return payload


def request_ai_chat(
    *,
    settings: Settings,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> AIChatResult | None:
    runtime = resolve_ai_runtime(settings)
    if not can_use_ai(settings):
        return None

    payload = build_chat_payload(
        runtime=runtime,
        messages=messages,
        temperature=temperature,
        model=model,
        max_tokens=max_tokens,
    )
    endpoint = f"{runtime.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {runtime.api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=runtime.timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("AI gateway request failed: %s", exc)
        return None

    try:
        raw = response.json()
        content = extract_content(raw)
        reasoning_content = extract_reasoning_content(raw)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("AI gateway response parsing failed: %s", exc)
        return None

    return AIChatResult(
        provider=detect_provider(runtime),
        model=str(raw.get("model") or payload["model"]),
        content=content,
        reasoning_content=reasoning_content,
        raw_response=raw,
    )


def request_ai_json(
    *,
    settings: Settings,
    system_prompt: str,
    user_payload: dict[str, Any],
    temperature: float | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any] | None:
    result = request_ai_chat(
        settings=settings,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        temperature=temperature,
        model=model,
        max_tokens=max_tokens,
    )
    if result is None:
        return None
    try:
        return parse_json_blob(result.content)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("AI JSON parsing failed: %s", exc)
        return None


def extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("missing message")

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        if text_parts:
            return "\n".join(text_parts)
    raise ValueError("missing content")


def extract_reasoning_content(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None

    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        return reasoning_content
    if isinstance(reasoning_content, list):
        text_parts = []
        for item in reasoning_content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        if text_parts:
            return "\n".join(text_parts)
    return None


def parse_json_blob(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return json.loads(cleaned)
