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
    service = request.app.state.whapi_service
    store = request.app.state.idempotency_store

    async def send() -> WhapiResult:
        return await service.send_text(payload.phone, build_high_intent_message(payload))

    try:
        result, already_sent = await store.run_once(payload.call_id, send)
    except (WhapiProviderError, ValueError):
        logger.error(
            "high_intent_whatsapp_failed",
            extra={
                "call_id": payload.call_id,
                "phone": payload.phone,
                "operation": "send_high_intent_whatsapp",
                "status": "failed",
                "error": "whapi_send_failed",
            },
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
    except ValueError:
        return {"success": False, "error": "invalid_phone"}
    except Exception:
        logger.error("complete_call_failed")
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
    except ValueError:
        return {"success": False, "error": "invalid_callback_request"}
    except Exception:
        logger.error("schedule_callback_failed")
        return {"success": False, "error": "callback_schedule_failed"}
