from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from app.config import Settings
from app.main import create_app
from app.services.followup_service import FollowupResult


class CompleteCallService:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def complete_call(self, request: object) -> FollowupResult:
        self.requests.append(request)
        return FollowupResult(
            success=True,
            text_sent=True,
            resume_sent=True,
            architecture_sent=True,
        )


@asynccontextmanager
async def client_for(service: CompleteCallService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        settings=Settings(_env_file=None, sarvam_tool_secret="test-secret"),
        call_service=service,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_complete_call_returns_component_delivery_results() -> None:
    service = CompleteCallService()
    payload = {
        "call_id": "call-1",
        "phone": "8688664337",
        "language": "Hindi",
        "business_type": "fashion",
        "products_sold": ["clothes"],
        "product_count": "200",
        "required_features": ["payments", "inventory"],
        "budget_range": "₹80,000",
        "timeline": "2 weeks",
        "urgency": "high",
        "decision_maker": "self",
        "objections": [],
        "lead_classification": "HOT",
        "classification_reason": "Clear budget",
        "important_statements": ["Launch within two weeks"],
        "summary": "Customer wants a fashion website.",
    }
    async with client_for(service) as client:
        response = await client.post(
            "/tools/complete-call",
            json=payload,
            headers={"X-Tool-Secret": "test-secret"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "text_sent": True,
        "resume_sent": True,
        "architecture_sent": True,
    }
    assert len(service.requests) == 1


async def test_complete_call_without_database_or_injected_service_is_structured() -> None:
    app = create_app(settings=Settings(_env_file=None, sarvam_tool_secret="test-secret"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/tools/complete-call",
            json={"call_id": "call-1", "phone": "8688664337"},
            headers={"X-Tool-Secret": "test-secret"},
        )
    assert response.json() == {"success": False, "error": "database_not_configured"}
