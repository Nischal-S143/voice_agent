from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import Call, Callback, CallbackStatus, CallDirection, EventType, Lead
from app.schemas.complete_call import CompleteCallRequest
from app.services.call_service import CallService
from app.services.followup_service import FollowupResult
from app.services.lead_service import LeadService


class Leads:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def upsert_by_phone(self, normalized_phone: str, **values: Any) -> Lead:
        self.values = {"normalized_phone": normalized_phone, **values}
        return Lead(id=7, normalized_phone=normalized_phone)


class Calls:
    def __init__(self, existing: Call | None = None) -> None:
        self.existing = existing
        self.upserts: list[dict[str, Any]] = []

    async def get_by_sarvam_call_id(self, sarvam_call_id: str) -> Call | None:
        return self.existing

    async def upsert_by_sarvam_call_id(self, sarvam_call_id: str, **values: Any) -> Call:
        self.upserts.append({"sarvam_call_id": sarvam_call_id, **values})
        return Call(
            id=self.existing.id if self.existing else 11,
            sarvam_call_id=sarvam_call_id,
            callback_id=self.existing.callback_id if self.existing else None,
            **{key: value for key, value in values.items() if key != "callback_id"},
        )


class Callbacks:
    def __init__(self, closable: bool = True) -> None:
        self.closable = closable
        self.completed: list[int] = []

    async def mark_completed(self, callback_id: int, *, now: datetime) -> Callback | None:
        self.completed.append(callback_id)
        if not self.closable:
            return None
        return Callback(
            id=callback_id,
            lead_id=7,
            source_call_id=11,
            requested_expression="now",
            scheduled_at=now,
            timezone="Asia/Kolkata",
            status=CallbackStatus.COMPLETED,
        )


class Events:
    def __init__(self) -> None:
        self.appended: list[EventType] = []

    async def append(self, *, lead_id: int, event_type: EventType, call_id: int | None = None, payload: dict[str, object] | None = None) -> None:
        self.appended.append(event_type)


class Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class Followup:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, str]] = []

    async def send_for_call(self, lead_id: int, call_id: int, phone: str, message: str) -> FollowupResult:
        self.calls.append((lead_id, call_id, phone))
        return FollowupResult(
            success=True, text_sent=True, resume_sent=True, architecture_sent=True
        )


def _service(calls: Calls, callbacks: Callbacks, events: Events, followup: Followup) -> CallService:
    return CallService(
        Session(),
        LeadService(Leads()),
        calls,
        callbacks,
        events,
        followup,
        "Nischal Saxena",
        "+919999999999",
    )


def _request(call_id: str = "call-1") -> CompleteCallRequest:
    return CompleteCallRequest(
        call_id=call_id,
        phone="8688664337",
        business_type="jewellery",
        product_count="200",
        summary="Wants a jewellery store",
    )


async def test_an_initial_call_completes_and_triggers_the_post_call_followup() -> None:
    """Catches a finished call that never gets its summary, resume, and architecture."""
    calls, callbacks, events, followup = Calls(), Callbacks(), Events(), Followup()

    result = await _service(calls, callbacks, events, followup).complete_call(_request())

    assert result.success is True
    assert calls.upserts[0]["direction"] is CallDirection.INITIAL
    assert calls.upserts[0]["status"] == "completed"
    assert events.appended == [EventType.CALL_COMPLETED]
    assert callbacks.completed == []
    assert followup.calls == [(7, 11, "8688664337")]


async def test_a_completed_callback_call_closes_its_callback() -> None:
    """Catches the final step of the callback flow: the callback never reaches COMPLETED."""
    existing = Call(
        id=42,
        lead_id=7,
        callback_id=19,
        sarvam_call_id="cb-19-abc",
        direction=CallDirection.CALLBACK,
    )
    calls, callbacks, events, followup = Calls(existing), Callbacks(), Events(), Followup()

    await _service(calls, callbacks, events, followup).complete_call(_request("cb-19-abc"))

    assert callbacks.completed == [19]
    assert events.appended == [EventType.CALL_COMPLETED, EventType.CALLBACK_COMPLETED]


async def test_completing_a_callback_call_keeps_its_direction_and_link() -> None:
    """Catches a callback call being relabelled INITIAL by the completion payload."""
    existing = Call(
        id=42,
        lead_id=7,
        callback_id=19,
        sarvam_call_id="cb-19-abc",
        direction=CallDirection.CALLBACK,
    )
    calls = Calls(existing)

    await _service(calls, Callbacks(), Events(), Followup()).complete_call(
        _request("cb-19-abc")
    )

    assert calls.upserts[0]["direction"] is CallDirection.CALLBACK


async def test_a_replayed_completion_does_not_re_audit_a_settled_callback() -> None:
    """Catches a duplicate completion payload writing a second CALLBACK_COMPLETED event."""
    existing = Call(
        id=42,
        lead_id=7,
        callback_id=19,
        sarvam_call_id="cb-19-abc",
        direction=CallDirection.CALLBACK,
    )
    events = Events()

    await _service(Calls(existing), Callbacks(closable=False), events, Followup()).complete_call(
        _request("cb-19-abc")
    )

    assert events.appended == [EventType.CALL_COMPLETED]


async def test_the_lead_is_written_through_the_lead_service_with_a_normalized_phone() -> None:
    """Catches a completion storing a raw ten-digit number the WhatsApp side cannot use."""
    leads = Leads()
    service = CallService(
        Session(), LeadService(leads), Calls(), Callbacks(), Events(), Followup(), "Nischal Saxena"
    )

    await service.complete_call(_request())

    assert leads.values["normalized_phone"] == "918688664337"
    assert leads.values["product_count"] == 200
    assert leads.values["business_type"] == "jewellery"


async def test_the_call_is_persisted_before_any_whatsapp_is_attempted() -> None:
    """Catches a WhatsApp failure rolling back the qualification the call captured."""
    session = Session()
    followup = Followup()
    commits_at_followup: list[int] = []

    async def watching(lead_id: int, call_id: int, phone: str, message: str) -> FollowupResult:
        commits_at_followup.append(session.commits)
        return await Followup().send_for_call(lead_id, call_id, phone, message)

    followup.send_for_call = watching  # type: ignore[method-assign]
    service = CallService(
        session, LeadService(Leads()), Calls(), Callbacks(), Events(), followup, "Nischal Saxena"
    )

    await service.complete_call(_request())

    assert commits_at_followup == [1]

