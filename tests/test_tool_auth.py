from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.services.whapi_service import WhapiResult


class FakeWhapiService:
    async def send_text(self, phone: str, text: str) -> WhapiResult:
        return WhapiResult(message_id="provider-1")


def valid_payload() -> dict[str, object]:
    return {"call_id": "call-1", "phone": "8688664337"}


@asynccontextmanager
async def client_for(secret: str = "configured-secret") -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        whapi_service=FakeWhapiService(),
        settings=Settings(_env_file=None, sarvam_tool_secret=secret),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_secret", "headers"),
    [
        ("configured-secret", {}),
        ("configured-secret", {"X-Tool-Secret": "wrong-secret"}),
        ("", {"X-Tool-Secret": "any-secret"}),
    ],
)
async def test_missing_wrong_and_unconfigured_tool_secrets_are_indistinguishable(
    configured_secret: str, headers: dict[str, str]
) -> None:
    """Catches secret branches that disclose whether tool authentication is configured."""
    async with client_for(configured_secret) as client:
        response = await client.post(
            "/tools/send-high-intent-whatsapp", json=valid_payload(), headers=headers
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


@pytest.mark.asyncio
async def test_correct_tool_secret_reaches_protected_tool_handler() -> None:
    """Catches an authentication dependency that rejects the configured secret."""
    async with client_for() as client:
        response = await client.post(
            "/tools/send-high-intent-whatsapp",
            json=valid_payload(),
            headers={"X-Tool-Secret": "configured-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message_id": "provider-1",
        "already_sent": False,
    }
