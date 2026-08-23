"""Place one real outbound call through the configured Sarvam adapter.

This exercises the same code path the callback scheduler uses, and prints the
raw request and response so an unexpected payload shape is visible.

    python scripts/test_outbound_call.py +919999999999             # fresh sales call
    python scripts/test_outbound_call.py +919999999999 --callback  # as a callback

A fresh call sends no previous-call context, which is what the agent sees on a
first outbound. `--callback` replays the context injection the scheduler does,
so the agent should reference the earlier conversation.

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

CALLBACK_CONTEXT: dict[str, object] = {
    "is_callback": True,
    "previous_business_type": "fashion",
    "previous_budget": "80k-1L",
    "previous_features": ["payment gateway", "COD"],
    "previous_summary": "Instagram seller moving to their own store.",
    "previous_objection": None,
}


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
    args = sys.argv[1:]
    as_callback = "--callback" in args
    phones = [arg for arg in args if not arg.startswith("--")]
    if not phones:
        print("usage: python scripts/test_outbound_call.py <phone> [--callback]")
        return 2

    settings = get_settings()
    if not _sarvam_outbound_configured(settings):
        print("Sarvam outbound is not fully configured; check the SARVAM_* vars.")
        return 2

    print(f"Placing a {'callback' if as_callback else 'fresh'} call to {phones[0]}\n")
    async with httpx.AsyncClient() as inner:
        caller = SarvamHttpOutboundCaller(LoggingClient(inner), settings)
        result = await caller.place_call(
            OutboundCallRequest(
                callback_id=999,
                phone=phones[0],
                context=dict(CALLBACK_CONTEXT) if as_callback else {},
            )
        )

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
