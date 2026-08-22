import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from app.main import create_app
from app.config import Settings
from app.services.whapi_service import WhapiProviderError, WhapiResult


class FakeWhapiService:
    def __init__(self, *, fail: bool = False, delay: float = 0) -> None:
        self.fail = fail
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def send_text(self, phone: str, text: str) -> WhapiResult:
        self.calls.append((phone, text))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise WhapiProviderError("whapi_request_failed")
        return WhapiResult(message_id="provider-1")


@asynccontextmanager
async def app_client(service: FakeWhapiService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        whapi_service=service,
        settings=Settings(_env_file=None, sarvam_tool_secret="test-tool-secret"),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tool-Secret": "test-tool-secret"},
    ) as client:
        yield client


def payload(call_id: str = "call-1") -> dict[str, object]:
    return {
        "call_id": call_id,
        "phone": "+91 86886 64337",
        "business_type": "fashion",
        "product_count": "200",
        "required_features": ["payments", "inventory"],
        "budget_range": "₹80,000",
        "timeline": "two weeks",
        "summary": "Customer wants an e-commerce website.",
    }


@pytest.mark.asyncio
async def test_success_returns_provider_message_id() -> None:
    service = FakeWhapiService()
    async with app_client(service) as client:
        response = await client.post("/tools/send-high-intent-whatsapp", json=payload())

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message_id": "provider-1",
        "already_sent": False,
    }
    assert len(service.calls) == 1


@pytest.mark.asyncio
async def test_duplicate_call_id_does_not_send_twice() -> None:
    service = FakeWhapiService()
    async with app_client(service) as client:
        first = await client.post("/tools/send-high-intent-whatsapp", json=payload())
        second = await client.post("/tools/send-high-intent-whatsapp", json=payload())

    assert first.json()["already_sent"] is False
    assert second.json() == {"success": True, "already_sent": True}
    assert len(service.calls) == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_call_id_shares_one_send() -> None:
    service = FakeWhapiService(delay=0.01)
    async with app_client(service) as client:
        first, second = await asyncio.gather(
            client.post("/tools/send-high-intent-whatsapp", json=payload()),
            client.post("/tools/send-high-intent-whatsapp", json=payload()),
        )

    responses = [first.json(), second.json()]
    assert len(service.calls) == 1
    assert sum(response.get("already_sent") is False for response in responses) == 1
    assert sum(response.get("already_sent") is True for response in responses) == 1


@pytest.mark.asyncio
async def test_provider_failure_is_structured_and_retryable() -> None:
    service = FakeWhapiService(fail=True)
    async with app_client(service) as client:
        failed = await client.post("/tools/send-high-intent-whatsapp", json=payload())
        service.fail = False
        retried = await client.post("/tools/send-high-intent-whatsapp", json=payload())

    assert failed.status_code == 200
    assert failed.json() == {"success": False, "error": "whapi_send_failed"}
    assert retried.json()["success"] is True
    assert len(service.calls) == 2


@pytest.mark.asyncio
async def test_health_is_available_without_provider_credentials() -> None:
    async with app_client(FakeWhapiService()) as client:
        response = await client.get("/health")

    assert response.json() == {"status": "ok"}
