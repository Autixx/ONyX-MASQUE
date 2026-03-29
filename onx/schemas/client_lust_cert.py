from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class LustClientCertificateIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    csr_pem: str = Field(min_length=1)


class LustClientCertificateRead(ONXBaseModel):
    id: str
    device_id: str
    serial_number_hex: str
    fingerprint_sha256: str
    subject_text: str
    certificate_pem: str
    ca_certificate_pem: str
    not_before: datetime
    not_after: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime
