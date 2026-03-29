from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


SUPPORTED_TRANSPORT_TYPES = ("lust",)
DEFAULT_TRANSPORT_PRIORITY = ["lust"]


class TransportPackageRead(ONXBaseModel):
    id: str
    name: str | None
    user_id: str | None
    preferred_lust_service_id: str | None
    lust_enabled: bool
    split_tunnel_enabled: bool
    split_tunnel_country_code: str | None
    split_tunnel_routes_json: list[str]
    priority_order_json: list[str]
    last_reconciled_at: datetime | None
    last_reconcile_summary_json: dict | None
    created_at: datetime
    updated_at: datetime


class TransportPackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    preferred_lust_service_id: str | None = None
    lust_enabled: bool = True
    split_tunnel_enabled: bool = False
    split_tunnel_country_code: str | None = None
    split_tunnel_routes: list[str] = Field(default_factory=list)


class TransportPackageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    preferred_lust_service_id: str | None = None
    lust_enabled: bool | None = None
    split_tunnel_enabled: bool | None = None
    split_tunnel_country_code: str | None = None
    split_tunnel_routes: list[str] | None = None


class TransportPackageUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_lust_service_id: str | None = None
    lust_enabled: bool = True
    split_tunnel_enabled: bool = False
    split_tunnel_country_code: str | None = None
    split_tunnel_routes: list[str] = Field(default_factory=list)


class TransportPackageReconcileResponse(ONXBaseModel):
    package: TransportPackageRead
    summary: dict
