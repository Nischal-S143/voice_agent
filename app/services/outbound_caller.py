from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class OutboundCallRequest(BaseModel):
    callback_id: int
    phone: str
    context: dict[str, object]


class OutboundCallResult(BaseModel):
    success: bool
    call_id: str | None = None
    error: str | None = None
    retryable: bool = False


class SarvamOutboundCaller(Protocol):
    async def place_call(self, request: OutboundCallRequest) -> OutboundCallResult: ...


class UnconfiguredSarvamOutboundCaller:
    async def place_call(self, request: OutboundCallRequest) -> OutboundCallResult:
        return OutboundCallResult(
            success=False,
            error="sarvam_outbound_not_configured",
            retryable=False,
        )
