from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models import (
    Call,
    Callback,
    CallbackAttemptStatus,
    CallbackStatus,
    CallDirection,
    EventType,
    Lead,
)
from app.services.callback_service import RETRY_DELAY, CallbackService
from app.services.outbound_caller import OutboundCallRequest, OutboundCallResult

NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


class Session:
    def __init__(self, lead: Lead, source_call: Call) -> None:
        self._rows: dict[type, Any] = {Lead: lead, Call: source_call}
        self.commits = 0

    async def get(self, model: type, identifier: int) -> Any:
        return self._rows[model]

    async def commit(self) -> None:
        self.commits += 1


class Callbacks:
    def __init__(self, due: Callback | None) -> None:
        self._due = due
        self.dialled: list[Callback] = []
        self.failures: list[tuple[str, datetime | None]] = []

    async def claim_due(self, *, now: datetime) -> Callback | None:
        callback, self._due = self._due, None
        if callback is not None:
            callback.status = CallbackStatus.IN_PROGRESS
            callback.claimed_at = now
            callback.attempt_count += 1
        return callback

    async def mark_dialled(self, callback: Callback) -> None:
        callback.status = CallbackStatus.IN_PROGRESS
        callback.claimed_at = None
        self.dialled.append(callback)

    async def mark_failed(self, callback: Callback, *, error: str, next_attempt_at: datetime | None) -> None:
        callback.status = (
            CallbackStatus.PENDING if next_attempt_at else CallbackStatus.FAILED
        )
        callback.claimed_at = None
        self.failures.append((error, next_attempt_at))


class Calls:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    async def upsert_by_sarvam_call_id(self, sarvam_call_id: str, **values: Any) -> Call:
        self.upserts.append({"sarvam_call_id": sarvam_call_id, **values})
        return Call(id=42, sarvam_call_id=sarvam_call_id, **values)


class Attempts:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **values: Any) -> None:
        self.records.append(values)


class Events:
    def __init__(self) -> None:
        self.appended: list[EventType] = []

    async def append(self, *, lead_id: int, event_type: EventType, call_id: int | None = None, payload: dict[str, object] | None = None) -> None:
        self.appended.append(event_type)


class Outbound:
    def __init__(self, result: OutboundCallResult) -> None:
        self.result = result
        self.requests: list[OutboundCallRequest] = []

    async def place_call(self, request: OutboundCallRequest) -> OutboundCallResult:
        self.requests.append(request)
        return self.result


def _fixtures(due: Callback | None, result: OutboundCallResult) -> tuple[CallbackService, dict[str, Any]]:
    lead = Lead(
        id=7,
        normalized_phone="918688664337",
        business_type="jewellery",
        product_count=200,
        budget="80k",
        timeline="2 weeks",
        required_features=["payments"],
        objections=["price"],
    )
    source_call = Call(
        id=11, lead_id=7, sarvam_call_id="call-1", direction=CallDirection.INITIAL,
        summary="Wants a jewellery store",
    )
    parts = {
        "session": Session(lead, source_call),
        "callbacks": Callbacks(due),
        "calls": Calls(),
        "attempts": Attempts(),
        "events": Events(),
        "outbound": Outbound(result),
        "lead": lead,
    }
    service = CallbackService(
        parts["session"],
        lead_service=None,
        calls=parts["calls"],
        callbacks=parts["callbacks"],
        attempts=parts["attempts"],
        events=parts["events"],
        outbound=parts["outbound"],
    )
    return service, parts


def _due_callback() -> Callback:
    return Callback(
        id=19,
        lead_id=7,
        source_call_id=11,
        requested_expression="in 10 minutes",
        scheduled_at=NOW - timedelta(minutes=1),
        timezone="Asia/Kolkata",
        status=CallbackStatus.PENDING,
        attempt_count=0,
    )


async def test_an_idle_tick_does_no_work() -> None:
    """Catches the 15-second worker tick dialling or writing when nothing is due."""
    service, parts = _fixtures(None, OutboundCallResult(success=True, call_id="cb-19-x"))

    assert await service.process_due() is False
    assert parts["outbound"].requests == []
    assert parts["events"].appended == []


async def test_a_placed_call_stays_in_progress_until_the_call_reports_completion() -> None:
    """Catches the worker marking a callback done the moment it is dialled."""
    callback = _due_callback()
    service, parts = _fixtures(
        callback,
        OutboundCallResult(success=True, call_id="cb-19-abc", provider_attempt_id="sarvam-att-1"),
    )

    assert await service.process_due() is True

    assert callback.status is CallbackStatus.IN_PROGRESS
    assert callback.completed_at is None
    assert parts["callbacks"].dialled == [callback]
    assert parts["events"].appended == [
        EventType.CALLBACK_ATTEMPTED,
        EventType.CALLBACK_TRIGGERED,
    ]


async def test_the_placed_call_is_recorded_as_a_callback_that_names_its_callback_row() -> None:
    """Catches an outbound call that /tools/complete-call cannot trace back to its callback."""
    callback = _due_callback()
    service, parts = _fixtures(
        callback, OutboundCallResult(success=True, call_id="cb-19-abc")
    )

    await service.process_due()

    upsert = parts["calls"].upserts[0]
    assert upsert["sarvam_call_id"] == "cb-19-abc"
    assert upsert["direction"] is CallDirection.CALLBACK
    assert upsert["callback_id"] == 19
    assert upsert["lead_id"] == 7


async def test_each_dial_is_recorded_against_its_attempt_number() -> None:
    """Catches per-attempt provider outcomes never reaching callback_attempts."""
    callback = _due_callback()
    service, parts = _fixtures(
        callback,
        OutboundCallResult(success=True, call_id="cb-19-abc", provider_attempt_id="sarvam-att-1"),
    )

    await service.process_due()

    assert parts["attempts"].records == [
        {
            "callback_id": 19,
            "attempt_number": 1,
            "status": CallbackAttemptStatus.PLACED,
            "call_id": 42,
            "provider_attempt_id": "sarvam-att-1",
        }
    ]


async def test_a_retryable_failure_requeues_the_callback_and_records_the_attempt() -> None:
    """Catches a transient Sarvam outage permanently writing off a promised callback."""
    callback = _due_callback()
    service, parts = _fixtures(
        callback,
        OutboundCallResult(
            success=False, error="sarvam_outbound_unavailable", retryable=True
        ),
    )

    await service.process_due()

    assert callback.status is CallbackStatus.PENDING
    error, next_attempt_at = parts["callbacks"].failures[0]
    assert error == "sarvam_outbound_unavailable"
    assert next_attempt_at is not None
    assert next_attempt_at - NOW >= RETRY_DELAY - timedelta(seconds=5)
    assert parts["attempts"].records[0]["status"] is CallbackAttemptStatus.FAILED
    assert parts["attempts"].records[0]["retryable"] is True
    assert parts["events"].appended[-1] is EventType.CALLBACK_FAILED
    assert parts["calls"].upserts == []


async def test_a_permanent_failure_stops_the_callback_without_a_retry_time() -> None:
    """Catches an unconfigured or rejected outbound looping on the worker forever."""
    callback = _due_callback()
    service, parts = _fixtures(
        callback,
        OutboundCallResult(
            success=False, error="sarvam_outbound_not_configured", retryable=False
        ),
    )

    await service.process_due()

    assert callback.status is CallbackStatus.FAILED
    assert parts["callbacks"].failures == [("sarvam_outbound_not_configured", None)]


async def test_the_callback_agent_opens_with_the_previous_conversation() -> None:
    """Catches a callback that re-qualifies a lead already qualified on the first call."""
    service, parts = _fixtures(
        _due_callback(), OutboundCallResult(success=True, call_id="cb-19-abc")
    )

    await service.process_due()

    request = parts["outbound"].requests[0]
    assert request.phone == "918688664337"
    assert request.context == {
        "is_callback": True,
        "previous_business_type": "jewellery",
        "previous_product_count": 200,
        "previous_budget": "80k",
        "previous_timeline": "2 weeks",
        "previous_features": ["payments"],
        "previous_objection": "price",
        "previous_summary": "Wants a jewellery store",
    }


async def test_the_claim_is_committed_before_the_call_is_placed() -> None:
    """Catches a crash between claim and dial leaving the callback eligible to dial twice."""
    callback = _due_callback()
    service, parts = _fixtures(
        callback, OutboundCallResult(success=True, call_id="cb-19-abc")
    )
    session = parts["session"]
    commits_at_dial: list[int] = []

    original = parts["outbound"].place_call

    async def watching(request: OutboundCallRequest) -> OutboundCallResult:
        commits_at_dial.append(session.commits)
        return await original(request)

    parts["outbound"].place_call = watching  # type: ignore[method-assign]

    await service.process_due()

    assert commits_at_dial == [1]
    assert session.commits == 2
