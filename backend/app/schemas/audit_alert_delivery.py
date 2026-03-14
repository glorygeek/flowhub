from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditAlertDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telemetry_event_id: int
    workflow_id: int | None = None
    run_id: str
    destination: str
    status: str
    attempt_count: int
    response_status_code: int | None = None
    response_body_preview: str
    error_message: str
    payload: dict
    delivered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
