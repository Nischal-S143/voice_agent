from __future__ import annotations

from typing import Any

from app.models import CallDirection, MessageKind
from app.repositories import (
    AuditEventRepository,
    CallbackAttemptRepository,
    CallbackRepository,
    CallRepository,
    LeadRepository,
    MessageRepository,
)
from app.services.call_service import CallService
from app.services.callback_service import CallbackService
from app.services.followup_service import FollowupService
from app.services.lead_service import LeadService
from app.services.message_builder import build_high_intent_message
from app.services.message_service import MessageService
from app.services.storage_service import StorageServiceError


class UnavailableStorage:
    async def create_signed_url(self, object_path: str) -> str:
        raise StorageServiceError("storage_not_configured")


class ConfiguredCallService:
    def __init__(self, session_factory: Any, whapi: Any, storage: Any, settings: Any) -> None:
        self._sessions = session_factory
        self._whapi = whapi
        self._storage = storage
        self._settings = settings

    async def complete_call(self, request: Any) -> Any:
        async with self._sessions() as session:
            messages = MessageService(
                MessageRepository(session), AuditEventRepository(session), session
            )
            followup = FollowupService(
                self._whapi,
                self._storage,
                messages,
                self._settings.supabase_resume_object_path,
                self._settings.supabase_architecture_object_path,
            )
            return await CallService(
                session,
                LeadService(LeadRepository(session)),
                CallRepository(session),
                CallbackRepository(session),
                AuditEventRepository(session),
                followup,
                self._settings.developer_name,
                self._settings.developer_phone,
            ).complete_call(request)


class ConfiguredCallbackService:
    def __init__(self, session_factory: Any, outbound: Any) -> None:
        self._sessions = session_factory
        self._outbound = outbound

    async def schedule(self, request: Any) -> dict[str, object]:
        async with self._sessions() as session:
            return await self._service(session).schedule(request)

    async def process_due(self) -> bool:
        async with self._sessions() as session:
            return await self._service(session).process_due()

    def _service(self, session: Any) -> CallbackService:
        return CallbackService(
            session,
            LeadService(LeadRepository(session)),
            CallRepository(session),
            CallbackRepository(session),
            CallbackAttemptRepository(session),
            AuditEventRepository(session),
            self._outbound,
        )


class PersistentHighIntentService:
    """Mid-call WhatsApp: capture what is known so far, then send once."""

    def __init__(self, session_factory: Any, whapi: Any, settings: Any = None) -> None:
        self._sessions = session_factory
        self._whapi = whapi
        self._settings = settings

    async def send(self, request: Any) -> dict[str, object]:
        async with self._sessions() as session:
            lead = await LeadService(LeadRepository(session)).upsert_from_high_intent(
                request
            )
            call = await CallRepository(session).upsert_by_sarvam_call_id(
                request.call_id,
                lead_id=lead.id,
                direction=CallDirection.INITIAL,
                status="active",
                summary=request.summary,
            )
            await session.commit()

            text = build_high_intent_message(
                request,
                getattr(self._settings, "developer_name", ""),
                getattr(self._settings, "developer_phone", ""),
            )
            messages = MessageService(
                MessageRepository(session), AuditEventRepository(session), session
            )
            outcome = await messages.deliver(
                lead_id=lead.id,
                call_id=call.id,
                kind=MessageKind.HIGH_INTENT,
                send=lambda: self._whapi.send_text(request.phone, text),
            )
            if not outcome.sent:
                return {"success": False, "error": outcome.error}
            if outcome.already_sent:
                return {"success": True, "already_sent": True}
            return {
                "success": True,
                "message_id": outcome.provider_message_id,
                "already_sent": False,
            }
