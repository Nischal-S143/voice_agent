from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models import MessageKind
from app.services.whapi_service import WhapiResult


class FollowupResult(BaseModel):
    success: bool
    text_sent: bool
    resume_sent: bool
    architecture_sent: bool


class FollowupService:
    """Post-call WhatsApp: the summary text, the resume, the architecture image.

    Each piece is delivered independently so one failing asset does not cost
    the lead the other two.
    """

    def __init__(
        self,
        whapi: Any,
        storage: Any,
        messages: Any,
        resume_object_path: str,
        architecture_object_path: str,
    ) -> None:
        self._whapi = whapi
        self._storage = storage
        self._messages = messages
        self._resume_path = resume_object_path
        self._architecture_path = architecture_object_path

    async def send_for_call(
        self, lead_id: int, call_id: int, phone: str, message: str
    ) -> FollowupResult:
        text_sent = await self._deliver(
            lead_id,
            call_id,
            MessageKind.FOLLOWUP_TEXT,
            lambda: self._whapi.send_text(phone, message),
        )
        resume_sent = await self._deliver(
            lead_id,
            call_id,
            MessageKind.FOLLOWUP_RESUME,
            lambda: self._send_resume(phone),
        )
        architecture_sent = await self._deliver(
            lead_id,
            call_id,
            MessageKind.FOLLOWUP_ARCHITECTURE,
            lambda: self._send_architecture(phone),
        )
        return FollowupResult(
            success=text_sent and resume_sent and architecture_sent,
            text_sent=text_sent,
            resume_sent=resume_sent,
            architecture_sent=architecture_sent,
        )

    async def _deliver(self, lead_id: int, call_id: int, kind: MessageKind, send: Any) -> bool:
        outcome = await self._messages.deliver(
            lead_id=lead_id, call_id=call_id, kind=kind, send=send
        )
        return outcome.sent

    async def _send_resume(self, phone: str) -> WhapiResult:
        url = await self._storage.create_signed_url(self._resume_path)
        return await self._whapi.send_document(
            phone, url, filename=self._resume_filename()
        )

    def _resume_filename(self) -> str:
        """Name the attachment after the stored object so it tracks the upload."""
        return self._resume_path.rsplit("/", 1)[-1] or "resume.pdf"

    async def _send_architecture(self, phone: str) -> WhapiResult:
        url = await self._storage.create_signed_url(self._architecture_path)
        return await self._whapi.send_image(
            phone,
            url,
            caption="Architecture overview of the voice sales agent.",
        )
