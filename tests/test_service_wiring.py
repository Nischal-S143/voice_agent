"""Drives the real service graph built by configured_services.

The unit tests hand each service its collaborators directly, so they cannot see
a constructor whose arguments were reordered or dropped during wiring. These
tests build the graph the application actually builds and run a whole request
through it, with only the AsyncSession and Whapi replaced.
"""
from __future__ import annotations

from typing import Any

from app.config import Settings
from app.models import Call, CallDirection, Lead, Message, MessageStatus
from app.schemas.complete_call import CompleteCallRequest
from app.schemas.whatsapp import HighIntentWhatsAppRequest
from app.services.configured_services import (
    ConfiguredCallService,
    PersistentHighIntentService,
)
from app.services.whapi_service import WhapiResult


class Result:
    def __init__(self, value: object | None) -> None:
        self._value = value

    def scalar_one(self) -> object:
        assert self._value is not None
        return self._value

    def scalar_one_or_none(self) -> object | None:
        return self._value


class FakeSession:
    """Answers each statement with the row PostgreSQL would return."""

    def __init__(self, existing_call: Call | None = None) -> None:
        self.existing_call = existing_call
        self.added: list[object] = []
        self.commits = 0
        self.reserved: list[str] = []

    async def execute(self, statement: Any) -> Result:
        table = getattr(statement, "table", None)
        if table is None:  # a SELECT, i.e. get_by_sarvam_call_id
            return Result(self.existing_call)
        name = table.name
        if name == "leads":
            return Result(Lead(id=7, normalized_phone="918688664337"))
        if name == "calls":
            return Result(
                Call(
                    id=11,
                    lead_id=7,
                    sarvam_call_id="call-1",
                    direction=CallDirection.INITIAL,
                )
            )
        if name == "messages":
            kind = statement.compile().params["kind"]
            if kind in self.reserved:
                return Result(None)
            self.reserved.append(kind)
            return Result(
                Message(
                    id=len(self.reserved),
                    lead_id=7,
                    call_id=11,
                    kind=kind,
                    status=MessageStatus.RESERVED,
                )
            )
        raise AssertionError(f"unexpected statement against {name}")

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class Whapi:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, phone: str, text: str) -> WhapiResult:
        self.sent.append("text")
        return WhapiResult("wamid-text")

    async def send_document(self, *args: object, **kwargs: object) -> WhapiResult:
        self.sent.append("document")
        return WhapiResult("wamid-doc")

    async def send_image(self, *args: object, **kwargs: object) -> WhapiResult:
        self.sent.append("image")
        return WhapiResult("wamid-image")


class Storage:
    async def create_signed_url(self, path: str) -> str:
        return f"https://signed.test/{path}"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        developer_name="Nischal Saxena",
        developer_phone="+919999999999",
    )


def _factory(session: FakeSession) -> Any:
    return lambda: session


async def test_complete_call_runs_the_whole_graph_and_sends_all_three_messages() -> None:
    """Catches a wiring break between the call, lead, message, and follow-up services."""
    session = FakeSession()
    whapi = Whapi()

    result = await ConfiguredCallService(
        _factory(session), whapi, Storage(), _settings()
    ).complete_call(
        CompleteCallRequest(
            call_id="call-1",
            phone="8688664337",
            business_type="jewellery",
            product_count="200",
            summary="Wants a jewellery store",
            important_statements=["Launch in two weeks"],
        )
    )

    assert result.model_dump() == {
        "success": True,
        "text_sent": True,
        "resume_sent": True,
        "architecture_sent": True,
    }
    assert whapi.sent == ["text", "document", "image"]
    assert session.reserved == [
        "FOLLOWUP_TEXT",
        "FOLLOWUP_RESUME",
        "FOLLOWUP_ARCHITECTURE",
    ]


async def test_the_follow_up_text_carries_the_developer_signature() -> None:
    """Catches the settings never reaching the message builder through the wiring."""
    session = FakeSession()
    sent: list[str] = []

    class Capturing(Whapi):
        async def send_text(self, phone: str, text: str) -> WhapiResult:
            sent.append(text)
            return await super().send_text(phone, text)

    await ConfiguredCallService(
        _factory(session), Capturing(), Storage(), _settings()
    ).complete_call(CompleteCallRequest(call_id="call-1", phone="8688664337"))

    assert "Nischal Saxena" in sent[0]
    assert "+919999999999" in sent[0]


async def test_high_intent_runs_the_graph_and_is_idempotent_per_call() -> None:
    """Catches the mid-call WhatsApp being sent twice when the agent repeats the tool call."""
    session = FakeSession()
    whapi = Whapi()
    service = PersistentHighIntentService(_factory(session), whapi, _settings())
    request = HighIntentWhatsAppRequest(
        call_id="call-1", phone="8688664337", business_type="jewellery"
    )

    first = await service.send(request)
    second = await service.send(request)

    assert first == {"success": True, "message_id": "wamid-text", "already_sent": False}
    assert second == {"success": True, "already_sent": True}
    assert whapi.sent == ["text"]
