from __future__ import annotations

from typing import Any

from app.models import CallDirection, EventType
from app.repositories import CallbackRepository, CallRepository, EventRepository, LeadRepository
from app.services.call_service import CallService
from app.services.callback_service import CallbackService
from app.services.followup_service import FollowupService
from app.services.storage_service import StorageServiceError
from app.services.whapi_service import WhapiProviderError
from app.utils.phone import normalize_indian_phone


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
            events = EventRepository(session)
            followup = FollowupService(
                self._whapi,
                self._storage,
                events,
                session,
                self._settings.supabase_resume_object_path,
                self._settings.supabase_architecture_object_path,
            )
            return await CallService(
                session,
                LeadRepository(session),
                CallRepository(session),
                events,
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
            LeadRepository(session),
            CallRepository(session),
            CallbackRepository(session),
            EventRepository(session),
            self._outbound,
        )


class PersistentHighIntentService:
    def __init__(self, session_factory: Any, whapi: Any, settings: Any = None) -> None:
        self._sessions = session_factory
        self._whapi = whapi
        self._settings = settings

    async def send(self, request: Any) -> dict[str, object]:
        from app.services.message_builder import build_high_intent_message

        async with self._sessions() as session:
            leads = LeadRepository(session)
            calls = CallRepository(session)
            events = EventRepository(session)
            count = int(request.product_count) if request.product_count and request.product_count.isdigit() else None
            lead = await leads.upsert_by_phone(
                normalize_indian_phone(request.phone),
                business_type=request.business_type,
                product_count=count,
                required_features=request.required_features,
                budget=request.budget_range,
                timeline=request.timeline,
            )
            call = await calls.upsert_by_sarvam_call_id(
                request.call_id,
                lead_id=lead.id,
                direction=CallDirection.INITIAL,
                status="active",
                summary=request.summary,
            )
            await session.commit()
            reserved = await events.reserve_delivery(
                lead_id=lead.id,
                call_id=call.id,
                target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
            )
            await session.commit()
            if not reserved:
                return {"success": True, "already_sent": True}
            try:
                result = await self._whapi.send_text(
                    request.phone,
                    build_high_intent_message(
                        request,
                        getattr(self._settings, "developer_name", ""),
                        getattr(self._settings, "developer_phone", ""),
                    ),
                )
            except (WhapiProviderError, ValueError):
                await events.release_delivery(
                    lead_id=lead.id,
                    call_id=call.id,
                    target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
                    payload={"error": "whapi_send_failed"},
                )
                await session.commit()
                return {"success": False, "error": "whapi_send_failed"}
            await events.complete_delivery(
                lead_id=lead.id,
                call_id=call.id,
                target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
                payload={"provider_message_id": result.message_id},
            )
            await session.commit()
            return {"success": True, "message_id": result.message_id, "already_sent": False}
