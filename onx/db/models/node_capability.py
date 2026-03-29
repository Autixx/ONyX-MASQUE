from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class NodeCapability(Base):
    __tablename__ = "node_capabilities"
    __table_args__ = (
        UniqueConstraint("node_id", "capability_name", name="uq_node_capability_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    capability_name: Mapped[str] = mapped_column(String(64), nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
