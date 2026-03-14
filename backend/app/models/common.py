from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ReviewStatus(str, Enum):
    draft = "draft"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class ExecutionMode(str, Enum):
    local = "local"
    remote = "remote"


class NodeExecutionStatus(str, Enum):
    success = "success"
    failed = "failed"
    skipped = "skipped"


class TimestampMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


risk_level_type = SQLEnum(RiskLevel, name="risk_level")
review_status_type = SQLEnum(ReviewStatus, name="review_status")
execution_mode_type = SQLEnum(ExecutionMode, name="execution_mode")
