from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.coercion import split_list, wrap_list


class CompleteCallRequest(BaseModel):
    call_id: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    language: str | None = None
    business_type: str | None = None
    products_sold: str | list[str] | None = None
    product_count: str | None = None
    required_features: list[str] = Field(default_factory=list)
    budget_range: str | None = None
    timeline: str | None = None
    urgency: str | None = None
    decision_maker: str | None = None
    objections: list[str] = Field(default_factory=list)
    lead_classification: str | None = None
    classification_reason: str | None = None
    callback_time: datetime | None = None
    important_statements: list[str] = Field(default_factory=list)
    summary: str | None = None
    transcript: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

    _split_lists = field_validator(
        "required_features", "objections", mode="before"
    )(staticmethod(split_list))
    _wrap_statements = field_validator("important_statements", mode="before")(
        staticmethod(wrap_list)
    )
