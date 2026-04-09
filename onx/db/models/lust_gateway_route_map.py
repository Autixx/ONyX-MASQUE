from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class LustGatewayRouteMap(Base):
    __tablename__ = "lust_gateway_route_maps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    gateway_service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lust_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    egress_pool_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lust_egress_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    destination_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
