from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LustClientSessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peer_id: str
    username: str
    service_id: str
    service_name: str
    node_id: str
    stream_path: str
    dns_resolver: str | None
    connected_at: datetime
    transport: str = "lust"
    protocol: str = "lust-h2"
