from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class TelemetryEvent(TimestampMixin, Base):
    __tablename__ = "telemetry_events"

    workflow_id: Mapped[int | None] = mapped_column(nullable=True)
    run_id: Mapped[str] = mapped_column(String(100), index=True)
    node_results: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    client_meta: Mapped[dict] = mapped_column(JSON, default=dict)
