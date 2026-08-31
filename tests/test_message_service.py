from __future__ import annotations

from app.models import EventType, Message, MessageKind, MessageStatus
from app.services.message_service import MessageService
from app.services.storage_service import StorageServiceError
from app.services.whapi_service import WhapiProviderError, WhapiResult


class Messages:
    """MessageRepository boundary that models the unique-key winner."""

    def __init__(self) -> None:
        self.rows: dict[tuple[int, MessageKind], Message] = {}

    async def reserve(self, *, lead_id: int, call_id: int, kind: MessageKind) -> Message | None:
        existing = self.rows.get((call_id, kind))
        if existing is not None and existing.status is not MessageStatus.FAILED:
            return None
        message = existing or Message(id=1, lead_id=lead_id, call_id=call_id, kind=kind)
        message.status = MessageStatus.RESERVED
        self.rows[(call_id, kind)] = message
        return message

    async def mark_sent(self, message: Message, *, provider_message_id: str, now: object) -> None:
        message.status = MessageStatus.SENT
        message.provider_message_id = provider_message_id

    async def mark_failed(self, message: Message, *, error: str) -> None:
        message.status = MessageStatus.FAILED
        message.last_error = error


class Events:
    def __init__(self) -> None:
        self.appended: list[EventType] = []
        self.payloads: list[dict[str, object] | None] = []

    async def append(self, *, lead_id: int, call_id: int | None = None, event_type: EventType, payload: dict[str, object] | None = None) -> None:
        self.appended.append(event_type)
        self.payloads.append(payload)


class Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _service(messages: Messages, events: Events, session: Session) -> MessageService:
    return MessageService(messages, events, session)


async def test_a_delivered_message_is_recorded_and_audited_as_sent() -> None:
    """Catches a provider result that never lands on the row or in the audit log."""
    messages, events, session = Messages(), Events(), Session()

    outcome = await _service(messages, events, session).deliver(
        lead_id=7,
        call_id=11,
        kind=MessageKind.HIGH_INTENT,
        send=lambda: _ok("wamid-1"),
    )

    assert outcome.sent is True
    assert outcome.already_sent is False
    assert outcome.provider_message_id == "wamid-1"
    assert messages.rows[(11, MessageKind.HIGH_INTENT)].status is MessageStatus.SENT
    assert events.appended == [
        EventType.HIGH_INTENT_WHATSAPP_REQUESTED,
        EventType.HIGH_INTENT_WHATSAPP_SENT,
    ]
    assert events.payloads[-1] == {"provider_message_id": "wamid-1"}


async def test_the_reservation_is_committed_before_the_provider_is_called() -> None:
    """Catches a crash mid-send leaving no record, which would let a retry send twice."""
    messages, events, session = Messages(), Events(), Session()
    commits_at_send: list[int] = []

    async def send() -> WhapiResult:
        commits_at_send.append(session.commits)
        return WhapiResult("wamid-1")

    await _service(messages, events, session).deliver(
        lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT, send=send
    )

    assert commits_at_send == [1]


async def test_a_duplicate_tool_call_for_the_same_call_never_reaches_the_provider() -> None:
    """Catches the lead being messaged twice when the agent repeats a tool call."""
    messages, events, session = Messages(), Events(), Session()
    service = _service(messages, events, session)
    sends = 0

    async def send() -> WhapiResult:
        nonlocal sends
        sends += 1
        return WhapiResult("wamid-1")

    first = await service.deliver(
        lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT, send=send
    )
    second = await service.deliver(
        lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT, send=send
    )

    assert sends == 1
    assert first.already_sent is False
    assert second.already_sent is True
    assert second.sent is True
    assert events.appended.count(EventType.HIGH_INTENT_WHATSAPP_SENT) == 1


async def test_a_provider_failure_is_audited_and_leaves_the_message_retryable() -> None:
    """Catches a transient Whapi error permanently blocking the message."""
    messages, events, session = Messages(), Events(), Session()
    service = _service(messages, events, session)

    async def failing() -> WhapiResult:
        raise WhapiProviderError("whapi_request_failed")

    outcome = await service.deliver(
        lead_id=7, call_id=11, kind=MessageKind.FOLLOWUP_TEXT, send=failing
    )

    assert outcome.sent is False
    assert outcome.error == "whapi_send_failed"
    assert events.appended == [
        EventType.FOLLOWUP_TEXT_REQUESTED,
        EventType.FOLLOWUP_TEXT_FAILED,
    ]

    retry = await service.deliver(
        lead_id=7, call_id=11, kind=MessageKind.FOLLOWUP_TEXT, send=lambda: _ok("wamid-2")
    )
    assert retry.sent is True
    assert retry.already_sent is False


async def test_an_unreachable_asset_fails_the_message_without_calling_whapi() -> None:
    """Catches a signed-URL outage being reported as a WhatsApp provider failure."""
    messages, events, session = Messages(), Events(), Session()

    async def failing() -> WhapiResult:
        raise StorageServiceError("storage_not_configured")

    outcome = await _service(messages, events, session).deliver(
        lead_id=7, call_id=11, kind=MessageKind.FOLLOWUP_RESUME, send=failing
    )

    assert outcome.sent is False
    assert outcome.error == "asset_url_failed"
    assert events.appended[-1] is EventType.FOLLOWUP_RESUME_FAILED


async def _ok(message_id: str) -> WhapiResult:
    return WhapiResult(message_id)
