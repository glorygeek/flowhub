from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class SkillTagLink(TimestampMixin, Base):
    __tablename__ = "skill_tag_links"
    __table_args__ = (
        UniqueConstraint("skill_id", "tag_id", "source", name="uq_skill_tag_source"),
    )

    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag_definitions.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="rule", index=True)
    confidence: Mapped[str] = mapped_column(String(16), default="high")
