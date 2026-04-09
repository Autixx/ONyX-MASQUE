from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class LustEgressPoolMember(ONXBaseModel):
    service_id: str
    weight: int = 100


class LustEgressPoolRead(ONXBaseModel):
    id: str
    name: str
    enabled: bool
    selection_strategy: str
    members_json: list[LustEgressPoolMember]
    description: str | None
    resolved_members: list[dict]
    created_at: datetime
    updated_at: datetime


class LustEgressPoolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    selection_strategy: str = Field(default="hash", min_length=1, max_length=32)
    members_json: list[LustEgressPoolMember] = Field(default_factory=list)
    description: str | None = None


class LustEgressPoolUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    selection_strategy: str | None = Field(default=None, min_length=1, max_length=32)
    members_json: list[LustEgressPoolMember] | None = None
    description: str | None = None


class LustGatewayRouteMapRead(ONXBaseModel):
    id: str
    name: str
    enabled: bool
    gateway_service_id: str
    gateway_service_name: str | None
    egress_pool_id: str
    egress_pool_name: str | None
    priority: int
    destination_country_code: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class LustGatewayRouteMapCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    gateway_service_id: str
    egress_pool_id: str
    priority: int = Field(default=100, ge=1, le=1000000)
    destination_country_code: str | None = Field(default=None, max_length=8)
    description: str | None = None


class LustGatewayRouteMapUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    gateway_service_id: str | None = None
    egress_pool_id: str | None = None
    priority: int | None = Field(default=None, ge=1, le=1000000)
    destination_country_code: str | None = Field(default=None, max_length=8)
    description: str | None = None
