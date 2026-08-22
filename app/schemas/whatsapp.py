from pydantic import BaseModel, Field


class HighIntentWhatsAppRequest(BaseModel):
    call_id: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    business_type: str | None = None
    product_count: str | None = None
    required_features: list[str] = Field(default_factory=list)
    budget_range: str | None = None
    timeline: str | None = None
    summary: str | None = None
