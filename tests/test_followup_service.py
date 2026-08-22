from app.models import EventType
from app.services.followup_service import FollowupService
from app.services.whapi_service import WhapiProviderError, WhapiResult


class Events:
    def __init__(self, already: set[EventType] | None = None) -> None:
        self.already = already or set()
        self.completed: list[EventType] = []
        self.released: list[EventType] = []

    async def reserve_delivery(self, **kwargs: object) -> bool:
        return kwargs["target_event_type"] not in self.already

    async def complete_delivery(self, **kwargs: object) -> bool:
        self.completed.append(kwargs["target_event_type"])
        self.already.add(kwargs["target_event_type"])
        return True

    async def release_delivery(self, **kwargs: object) -> bool:
        self.released.append(kwargs["target_event_type"])
        return True


class Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class Storage:
    async def create_signed_url(self, path: str) -> str:
        return f"https://signed.test/{path}"


class Whapi:
    def __init__(self, fail_document: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_document = fail_document

    async def send_text(self, phone: str, text: str) -> WhapiResult:
        self.calls.append("text")
        return WhapiResult("text-1")

    async def send_document(self, *args: object, **kwargs: object) -> WhapiResult:
        self.calls.append("document")
        if self.fail_document:
            raise WhapiProviderError("whapi_request_failed")
        return WhapiResult("document-1")

    async def send_image(self, *args: object, **kwargs: object) -> WhapiResult:
        self.calls.append("image")
        return WhapiResult("image-1")


async def test_followup_attempts_all_components_in_order_and_continues_after_failure() -> None:
    whapi = Whapi(fail_document=True)
    events = Events()
    result = await FollowupService(
        whapi, Storage(), events, Session(), "resume.pdf", "architecture.png"
    ).send_for_call(7, 11, "8688664337", "Hello")

    assert whapi.calls == ["text", "document", "image"]
    assert result.model_dump() == {
        "success": False,
        "text_sent": True,
        "resume_sent": False,
        "architecture_sent": True,
    }
    assert events.released == [EventType.FOLLOWUP_RESUME_SENT]


async def test_followup_retries_only_components_without_success_event() -> None:
    whapi = Whapi()
    events = Events({EventType.FOLLOWUP_TEXT_SENT, EventType.FOLLOWUP_ARCHITECTURE_SENT})
    result = await FollowupService(
        whapi, Storage(), events, Session(), "resume.pdf", "architecture.png"
    ).send_for_call(7, 11, "8688664337", "Hello")

    assert whapi.calls == ["document"]
    assert result.text_sent is True
    assert result.resume_sent is True
    assert result.architecture_sent is True
