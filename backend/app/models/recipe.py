from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import RiskLevel, ReviewStatus, TimestampMixin, review_status_type, risk_level_type


class Recipe(TimestampMixin, Base):
    __tablename__ = "recipes"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    scenario: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    node_skeleton: Mapped[list] = mapped_column(JSON, default=list)
    edges: Mapped[list] = mapped_column(JSON, default=list)
    param_mappings: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_skill_categories: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[RiskLevel] = mapped_column(risk_level_type, default=RiskLevel.low)
    status: Mapped[ReviewStatus] = mapped_column(review_status_type, default=ReviewStatus.draft)
