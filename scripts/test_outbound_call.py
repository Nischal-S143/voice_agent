"""Place one real outbound call through the configured Sarvam adapter.

This exercises the same code path the callback scheduler uses, and prints the
raw request and response so an unexpected payload shape is visible.

    python scripts/test_outbound_call.py +919999999999

WARNING: this dials a real phone number and consumes voice minutes.
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx

from app.config import get_settings
from app.main import _sarvam_outbound_configured
from app.services.outbound_caller import OutboundCallRequest, SarvamHttpOutboundCaller


class LoggingClient:
    """Wrap httpx so the adapter's exact request and response are visible."""

    def __init__(self, inner: httpx.AsyncClient) -> None:
        self._inner = inner

    async def post(self, url: str, **kwargs: object) -> httpx.Response:
        print("REQUEST URL:\n ", url)
        print("REQUEST BODY:\n", json.dumps(kwargs.get("json"), indent=2))
        response = await self._inner.post(url, **kwargs)
        print(f"\nRESPONSE STATUS: {response.status_code}")
        print("RESPONSE BODY:\n", response.text[:2000])
        return response


async def main() -> int:
    phone = sys.argv[1] if len(sys.argv) > 1 else ""
    if not phone:
        print("usage: python scripts/test_outbound_call.py <phone>")
        return 2

    settings = get_settings()
    if not _sarvam_outbound_configured(settings):
        print("Sarvam outbound is not fully configured; check the SARVAM_* vars.")
        return 2

    async with httpx.AsyncClient() as inner:
        caller = SarvamHttpOutboundCaller(LoggingClient(inner), settings)
        request = OutboundCallRequest(
            callback_id=999,
            phone=phone,
            context={
                "is_callback": True,
                "previous_business_type": "fashion",
                "previous_budget": "80k-1L",
                "previous_features": ["payment gateway", "COD"],
                "previous_summary": "Instagram seller moving to their own store.",
                "previous_objection": None,
            },
        )
        result = await caller.place_call(request)

    print("\n" + "=" * 50)
    print("ADAPTER RESULT:", result.model_dump())
    if not result.success and result.error == "sarvam_outbound_no_call_id":
        print(
            "\nThe call was accepted but no id was found in the response.\n"
            "Send the RESPONSE BODY above to Claude so _extract_call_id can be fixed."
        )
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
