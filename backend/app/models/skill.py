from datetime import datetime

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import (
    ExecutionMode,
    RiskLevel,
    ReviewStatus,
    TimestampMixin,
    execution_mode_type,
    review_status_type,
    risk_level_type,
)


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        execution_mode_type,
        default=ExecutionMode.local,
    )
    read_only: Mapped[bool] = mapped_column(Boolean, default=False)
    writes_external_state: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_level: Mapped[RiskLevel] = mapped_column(risk_level_type, default=RiskLevel.low)
    status: Mapped[ReviewStatus] = mapped_column(
        review_status_type,
        default=ReviewStatus.draft,
    )
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    source_slug: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(500))
    owner_handle: Mapped[str | None] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    summary: Mapped[str] = mapped_column(Text, default="")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    registry_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    source_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column()
