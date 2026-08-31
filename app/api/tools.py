import logging

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import verify_tool_secret
from app.schemas.whatsapp import HighIntentWhatsAppRequest
from app.schemas.complete_call import CompleteCallRequest
from app.schemas.callback import ScheduleCallbackRequest
from app.services.message_builder import build_high_intent_message
from app.services.whapi_service import WhapiProviderError, WhapiResult

router = APIRouter(
    prefix="/tools", tags=["tools"], dependencies=[Depends(verify_tool_secret)]
)
logger = logging.getLogger(__name__)


@router.post("/send-high-intent-whatsapp")
async def send_high_intent_whatsapp(
    payload: HighIntentWhatsAppRequest, request: Request
) -> dict[str, object]:
    persistent_service = getattr(request.app.state, "high_intent_service", None)
    if persistent_service is not None:
        return await persistent_service.send(payload)
    # No database: fall back to the in-process idempotency store, which cannot
    # survive a restart or span workers but still stops a repeated tool call.
    service = getattr(request.app.state, "whapi_service", None)
    if service is None:
        return {"success": False, "error": "whatsapp_not_configured"}
    store = request.app.state.idempotency_store

    async def send() -> WhapiResult:
        settings = request.app.state.settings
        return await service.send_text(
            payload.phone,
            build_high_intent_message(
                payload, settings.developer_name, settings.developer_phone
            ),
        )

    try:
        result, already_sent = await store.run_once(payload.call_id, send)
    except (WhapiProviderError, ValueError):
        logger.error(
            "high_intent_whatsapp_failed call_id=%s phone=%r",
            payload.call_id,
            payload.phone,
        )
        return {"success": False, "error": "whapi_send_failed"}

    if already_sent:
        return {"success": True, "already_sent": True}
    assert result is not None
    return {
        "success": True,
        "message_id": result.message_id,
        "already_sent": False,
    }


@router.post("/complete-call")
async def complete_call(
    payload: CompleteCallRequest, request: Request
) -> dict[str, object]:
    service = getattr(request.app.state, "call_service", None)
    if service is None:
        return {"success": False, "error": "database_not_configured"}
    try:
        result = await service.complete_call(payload)
    except ValueError as error:
        # Nothing was written, so without the rejected value there is no way to
        # tell a malformed number from a missing one after the call has ended.
        logger.error(
            "complete_call_rejected_phone call_id=%s phone=%r reason=%s",
            payload.call_id,
            payload.phone,
            error or "invalid_phone",
        )
        return {"success": False, "error": "invalid_phone"}
    except Exception:
        logger.exception("complete_call_failed call_id=%s", payload.call_id)
        return {"success": False, "error": "complete_call_failed"}
    return result.model_dump()


@router.post("/schedule-callback")
async def schedule_callback(
    payload: ScheduleCallbackRequest, request: Request
) -> dict[str, object]:
    service = getattr(request.app.state, "callback_service", None)
    if service is None:
        return {"success": False, "error": "database_not_configured"}
    if payload.callback_time is None:
        return {"success": False, "error": "callback_time_required"}
    try:
        return await service.schedule(payload)
    except ValueError as error:
        logger.error(
            "schedule_callback_rejected call_id=%s phone=%r reason=%s",
            payload.call_id,
            payload.phone,
            error or "invalid_callback_request",
        )
        return {"success": False, "error": "invalid_callback_request"}
    except Exception:
        logger.exception("schedule_callback_failed call_id=%s", payload.call_id)
        return {"success": False, "error": "callback_schedule_failed"}
