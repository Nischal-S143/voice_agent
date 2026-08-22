from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ScheduleCallbackRequest(BaseModel):
    call_id: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    requested_expression: str = Field(min_length=1)
    callback_time: datetime | None = None
    timezone: str = "Asia/Kolkata"
    lead_classification: str | None = None
    reason: str | None = None
    summary: str | None = None

    @field_validator("callback_time")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("callback_time_must_include_offset")
        return value
