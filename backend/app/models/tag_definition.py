from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class TagDefinition(TimestampMixin, Base):
    __tablename__ = "tag_definitions"

    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160), default="")
    category: Mapped[str] = mapped_column(String(64), default="keyword", index=True)
    source: Mapped[str] = mapped_column(String(32), default="rule", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
