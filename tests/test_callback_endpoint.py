from contextlib import asynccontextmanager

import httpx

from app.config import Settings
from app.main import create_app


class CallbackService:
    async def schedule(self, request: object) -> dict[str, object]:
        return {
            "success": True,
            "callback_id": "19",
            "scheduled_for": "2026-08-23T10:00:00+05:30",
        }


async def test_schedule_callback_requires_offset_aware_time() -> None:
    app = create_app(
        settings=Settings(_env_file=None, sarvam_tool_secret="secret"),
        callback_service=CallbackService(),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tools/schedule-callback",
            headers={"X-Tool-Secret": "secret"},
            json={
                "call_id": "call-1",
                "phone": "8688664337",
                "requested_expression": "tomorrow morning",
                "callback_time": "2026-08-23T10:00:00",
                "timezone": "Asia/Kolkata",
            },
        )
    assert response.status_code == 422


async def test_schedule_callback_returns_persisted_result() -> None:
    app = create_app(
        settings=Settings(_env_file=None, sarvam_tool_secret="secret"),
        callback_service=CallbackService(),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tools/schedule-callback",
            headers={"X-Tool-Secret": "secret"},
            json={
                "call_id": "call-1",
                "phone": "8688664337",
                "requested_expression": "tomorrow morning",
                "callback_time": "2026-08-23T10:00:00+05:30",
                "timezone": "Asia/Kolkata",
                "lead_classification": "WARM",
                "reason": "Discuss budget",
                "summary": "Interested",
            },
        )
    assert response.json() == {
        "success": True,
        "callback_id": "19",
        "scheduled_for": "2026-08-23T10:00:00+05:30",
    }
