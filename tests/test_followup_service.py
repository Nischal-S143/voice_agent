from app.models import MessageKind
from app.services.followup_service import FollowupService
from app.services.message_service import DeliveryOutcome
from app.services.whapi_service import WhapiProviderError, WhapiResult


class Messages:
    """MessageService boundary: already-sent kinds never reach the provider."""

    def __init__(self, already: set[MessageKind] | None = None) -> None:
        self.already = already or set()
        self.failed: list[MessageKind] = []

    async def deliver(self, *, lead_id: int, call_id: int, kind: MessageKind, send: object) -> DeliveryOutcome:
        if kind in self.already:
            return DeliveryOutcome(sent=True, already_sent=True)
        try:
            result = await send()
        except WhapiProviderError:
            self.failed.append(kind)
            return DeliveryOutcome(sent=False, error="whapi_send_failed")
        self.already.add(kind)
        return DeliveryOutcome(sent=True, provider_message_id=result.message_id)


class Storage:
    async def create_signed_url(self, path: str) -> str:
        return f"https://signed.test/{path}"


class Whapi:
    def __init__(self, fail_document: bool = False) -> None:
        self.calls: list[str] = []
        self.documents: list[dict[str, object]] = []
        self.fail_document = fail_document

    async def send_text(self, phone: str, text: str) -> WhapiResult:
        self.calls.append("text")
        return WhapiResult("text-1")

    async def send_document(self, *args: object, **kwargs: object) -> WhapiResult:
        self.calls.append("document")
        self.documents.append(kwargs)
        if self.fail_document:
            raise WhapiProviderError("whapi_request_failed")
        return WhapiResult("document-1")

    async def send_image(self, *args: object, **kwargs: object) -> WhapiResult:
        self.calls.append("image")
        return WhapiResult("image-1")


def _service(whapi: Whapi, messages: Messages) -> FollowupService:
    return FollowupService(
        whapi, Storage(), messages, "resume/Nischal_Saxena_Resume.pdf", "architecture.png"
    )


async def test_followup_attempts_all_components_in_order_and_continues_after_failure() -> None:
    """Catches one failing asset costing the lead the other two follow-up messages."""
    whapi = Whapi(fail_document=True)
    messages = Messages()

    result = await _service(whapi, messages).send_for_call(7, 11, "8688664337", "Hello")

    assert whapi.calls == ["text", "document", "image"]
    assert result.model_dump() == {
        "success": False,
        "text_sent": True,
        "resume_sent": False,
        "architecture_sent": True,
    }
    assert messages.failed == [MessageKind.FOLLOWUP_RESUME]


async def test_followup_retries_only_the_components_not_already_delivered() -> None:
    """Catches a retried completion payload sending the lead a second copy of everything."""
    whapi = Whapi()
    messages = Messages({MessageKind.FOLLOWUP_TEXT, MessageKind.FOLLOWUP_ARCHITECTURE})

    result = await _service(whapi, messages).send_for_call(7, 11, "8688664337", "Hello")

    assert whapi.calls == ["document"]
    assert result.success is True


async def test_resume_is_attached_under_the_stored_object_name() -> None:
    """Catches the lead receiving the resume as an unnamed or misnamed attachment."""
    whapi = Whapi()

    await _service(whapi, Messages()).send_for_call(7, 11, "8688664337", "Hello")

    assert whapi.documents[0]["filename"] == "Nischal_Saxena_Resume.pdf"
