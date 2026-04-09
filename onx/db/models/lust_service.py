from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class LustService(Base):
    __tablename__ = "lust_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="standalone", index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    listen_host: Mapped[str] = mapped_column(String(255), nullable=False, default="0.0.0.0")
    listen_port: Mapped[int] = mapped_column(Integer, nullable=False, default=443)
    public_host: Mapped[str] = mapped_column(String(255), nullable=False)
    public_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tls_server_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    h2_path: Mapped[str] = mapped_column(String(255), nullable=False, default="/lust")
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_scheme: Mapped[str] = mapped_column(String(32), nullable=False, default="bearer")
    acme_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_dns_resolver: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    selection_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    health_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
