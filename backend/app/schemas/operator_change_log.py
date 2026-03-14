from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OperatorChangeLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    action: str
    actor: str
    note: str
    before_state: dict
    after_state: dict
    created_at: datetime
