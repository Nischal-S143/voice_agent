from pydantic import BaseModel, Field, field_validator

from app.schemas.coercion import split_list


class HighIntentWhatsAppRequest(BaseModel):
    call_id: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    business_type: str | None = None
    product_count: str | None = None
    required_features: list[str] = Field(default_factory=list)
    budget_range: str | None = None
    timeline: str | None = None
    summary: str | None = None

    _split_features = field_validator("required_features", mode="before")(
        staticmethod(split_list)
    )
