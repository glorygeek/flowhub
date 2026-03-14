from datetime import datetime

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class AuditAlertDelivery(TimestampMixin, Base):
    __tablename__ = "audit_alert_deliveries"

    telemetry_event_id: Mapped[int] = mapped_column(Integer, index=True)
    workflow_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    run_id: Mapped[str] = mapped_column(String(100), index=True)
    destination: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), index=True, default="failed")
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_preview: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
