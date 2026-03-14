from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import ExecutionMode, TimestampMixin, execution_mode_type


class RunRequest(TimestampMixin, Base):
    __tablename__ = "run_requests"

    goal: Mapped[str] = mapped_column(Text, nullable=False)
    targets: Mapped[list] = mapped_column(JSON, default=list)
    credential_descriptors: Mapped[list] = mapped_column(JSON, default=list)
    output_format: Mapped[str] = mapped_column(String(32), default="json")
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        execution_mode_type,
        default=ExecutionMode.remote,
    )
    user_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    workflow_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    planning_notes: Mapped[list] = mapped_column(JSON, default=list)
