from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class LustServiceRead(ONXBaseModel):
    id: str
    name: str
    node_id: str
    role: str
    state: str
    listen_host: str
    listen_port: int
    public_host: str
    public_port: int | None
    tls_server_name: str | None
    h2_path: str
    use_tls: bool
    auth_scheme: str
    acme_email: str | None
    client_dns_resolver: str | None
    country_code: str | None
    selection_weight: int
    maintenance_mode: bool
    description: str | None
    desired_config_json: dict | None
    health_summary_json: dict | None
    last_error_text: str | None
    created_at: datetime
    updated_at: datetime


class LustServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    node_id: str
    role: str = Field(default="standalone", min_length=1, max_length=32)
    listen_host: str = Field(default="0.0.0.0", min_length=1, max_length=255)
    listen_port: int = Field(default=443, ge=1, le=65535)
    public_host: str = Field(min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    tls_server_name: str | None = Field(default=None, max_length=255)
    h2_path: str = Field(default="/lust", min_length=1, max_length=255)
    use_tls: bool = True
    auth_scheme: str = Field(default="bearer", min_length=1, max_length=32)
    acme_email: str | None = Field(default=None, max_length=255)
    client_dns_resolver: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, max_length=8)
    selection_weight: int = Field(default=100, ge=1, le=1000000)
    maintenance_mode: bool = False
    description: str | None = None
    desired_config_json: dict | None = None


class LustServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    node_id: str | None = None
    role: str | None = Field(default=None, min_length=1, max_length=32)
    state: str | None = Field(default=None, min_length=1, max_length=32)
    listen_host: str | None = Field(default=None, min_length=1, max_length=255)
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    public_host: str | None = Field(default=None, min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    tls_server_name: str | None = Field(default=None, max_length=255)
    h2_path: str | None = Field(default=None, min_length=1, max_length=255)
    use_tls: bool | None = None
    auth_scheme: str | None = Field(default=None, min_length=1, max_length=32)
    acme_email: str | None = Field(default=None, max_length=255)
    client_dns_resolver: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, max_length=8)
    selection_weight: int | None = Field(default=None, ge=1, le=1000000)
    maintenance_mode: bool | None = None
    description: str | None = None
    desired_config_json: dict | None = None
