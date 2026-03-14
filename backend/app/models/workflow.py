from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import RiskLevel, ReviewStatus, TimestampMixin, review_status_type, risk_level_type


class Workflow(TimestampMixin, Base):
    __tablename__ = "workflows"

    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    nodes: Mapped[list] = mapped_column(JSON, default=list)
    edges: Mapped[list] = mapped_column(JSON, default=list)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)
    source_recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(risk_level_type, default=RiskLevel.low)
    status: Mapped[ReviewStatus] = mapped_column(review_status_type, default=ReviewStatus.draft)
    retry_policy: Mapped[dict | None] = mapped_column(JSON, default=None)
    confirm_points: Mapped[list | None] = mapped_column(JSON, default=None)
    planner_decision_log: Mapped[list | None] = mapped_column(JSON, default=None)
