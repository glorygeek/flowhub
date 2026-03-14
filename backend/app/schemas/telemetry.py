from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.common import NodeExecutionStatus


class NodeExecutionResult(BaseModel):
    node_id: str = Field(min_length=1)
    status: NodeExecutionStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retry_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_failure_error(self):
        if self.status == NodeExecutionStatus.failed and not self.error:
            raise ValueError("Failed node result requires an error message.")
        return self


class TelemetryEventCreate(BaseModel):
    workflow_id: int | None = None
    run_id: str = Field(min_length=1, max_length=100)
    node_results: list[NodeExecutionResult] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    client_meta: dict[str, Any] = Field(default_factory=dict)


class TelemetryEventRead(TelemetryEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class TelemetryAck(BaseModel):
    accepted: bool
    ingested_at: datetime


class TelemetryAnomalyRead(BaseModel):
    event_id: int
    workflow_id: int | None = None
    run_id: str
    failed_node_count: int
    failed_node_ids: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    client_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TelemetryAlertDeliveryRead(BaseModel):
    id: int
    telemetry_event_id: int
    workflow_id: int | None = None
    run_id: str
    destination: str
    status: str
    attempt_count: int
    response_status_code: int | None = None
    response_body_preview: str = ""
    error_message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    delivered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
