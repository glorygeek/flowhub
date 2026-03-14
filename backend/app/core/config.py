from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FlowHub API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/flowhub.db"
    flowhub_api_key: str = "dev-flowhub-key"
    cors_allow_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    cors_allow_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    cors_allow_credentials: bool = False
    clawhub_registry_url: str = "https://clawhub.ai"
    clawhub_sync_enabled: bool = True
    clawhub_sync_on_startup: bool = False
    clawhub_sync_cron: str = "0 3 * * *"
    clawhub_sync_timezone: str = "Asia/Shanghai"
    clawhub_sync_page_size: int = 100
    clawhub_sync_timeout_seconds: float = 20.0
    clawhub_sync_max_retries: int = 8
    skill_search_remote_enabled: bool = True
    skill_search_default_limit: int = 24
    ai_enabled: bool = False
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    ai_timeout_seconds: float = 30.0
    ai_default_temperature: float = 0.2
    ai_thinking_enabled: bool = False
    planner_ai_enabled: bool = False
    planner_ai_base_url: str = "https://api.openai.com/v1"
    planner_ai_model: str = ""
    planner_ai_api_key: str = ""
    planner_ai_timeout_seconds: float = 30.0
    planner_ai_max_candidates: int = 8
    audit_alert_webhook_enabled: bool = False
    audit_alert_webhook_url: str = ""
    audit_alert_webhook_destinations_json: str = ""
    audit_alert_webhook_route_rules_json: str = ""
    audit_alert_webhook_timezone: str = "UTC"
    audit_alert_webhook_timeout_seconds: float = 5.0
    audit_alert_webhook_max_retries: int = 2
    audit_alert_webhook_retry_backoff_seconds: float = 1.0
    audit_alert_webhook_response_preview_chars: int = 800


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
