from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from supabase import create_client

from app.api.tools import router as tools_router
from app.config import Settings, get_settings
from app.database import create_engine_and_session_factory
from app.services.idempotency import InMemoryIdempotencyStore
from app.services.whapi_service import WhapiService
from app.services.configured_services import (
    ConfiguredCallbackService,
    ConfiguredCallService,
    PersistentHighIntentService,
    UnavailableStorage,
)
from app.services.outbound_caller import (
    SarvamHttpOutboundCaller,
    UnconfiguredSarvamOutboundCaller,
)
from app.services.storage_service import StorageService
from app.scheduler.scheduler import create_scheduler

logger = logging.getLogger(__name__)


def _sarvam_outbound_configured(settings: Settings) -> bool:
    """Every field below is required to address a single Instant Outbound call."""
    return all(
        (
            settings.sarvam_api_key.get_secret_value(),
            settings.sarvam_org_id,
            settings.sarvam_workspace_id,
            settings.sarvam_app_id,
            settings.sarvam_connection_id,
            settings.sarvam_agent_phone_number,
        )
    )


def _build_outbound_caller(settings: Settings, client: Any | None) -> Any:
    if client is None or not _sarvam_outbound_configured(settings):
        return UnconfiguredSarvamOutboundCaller()
    return SarvamHttpOutboundCaller(client, settings)


def create_app(
    whapi_service: Any | None = None,
    settings: Settings | None = None,
    call_service: Any | None = None,
    callback_service: Any | None = None,
) -> FastAPI:
    application_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, session_factory = create_engine_and_session_factory(application_settings)
        app.state.db_engine = engine
        app.state.session_factory = session_factory

        owned_client = None
        scheduler = None
        try:
            if whapi_service is None:
                owned_client = httpx.AsyncClient()
                app.state.whapi_service = WhapiService(
                    owned_client,
                    application_settings.whapi_base_url,
                    application_settings.whapi_token.get_secret_value(),
                )
            active_whapi = app.state.whapi_service
            storage: Any = UnavailableStorage()
            service_key = application_settings.supabase_service_role_key.get_secret_value()
            if application_settings.supabase_url and service_key:
                supabase_client = create_client(application_settings.supabase_url, service_key)
                storage = StorageService(
                    supabase_client,
                    application_settings.supabase_storage_bucket,
                    application_settings.callback_signed_url_ttl_seconds,
                )
            if session_factory is not None:
                app.state.high_intent_service = PersistentHighIntentService(
                    session_factory, active_whapi, application_settings
                )
                if app.state.call_service is None:
                    app.state.call_service = ConfiguredCallService(
                        session_factory, active_whapi, storage, application_settings
                    )
                if app.state.callback_service is None:
                    app.state.callback_service = ConfiguredCallbackService(
                        session_factory,
                        _build_outbound_caller(application_settings, owned_client),
                    )
                scheduler = create_scheduler(
                    app.state.callback_service,
                    application_settings.callback_poll_seconds,
                )
                scheduler.start()
            yield
        finally:
            if scheduler is not None and scheduler.running:
                scheduler.shutdown(wait=False)
            if owned_client is not None:
                await owned_client.aclose()
            if engine is not None:
                await engine.dispose()

    application = FastAPI(title="ElevateBox Whapi Integration", lifespan=lifespan)
    application.state.settings = application_settings
    application.state.call_service = call_service
    application.state.callback_service = callback_service
    application.state.high_intent_service = None
    application.state.idempotency_store = InMemoryIdempotencyStore()
    if whapi_service is not None:
        application.state.whapi_service = whapi_service
    @application.exception_handler(RequestValidationError)
    async def log_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Name the rejected fields in the logs; a bare 422 is undebuggable.

        Only field locations and error types are logged, never the submitted
        values, which carry customer phone numbers and conversation content.
        """
        problems = [
            {"field": ".".join(str(part) for part in error["loc"][1:]),
             "error": error["type"]}
            for error in exc.errors()
        ]
        logger.warning(
            "request_validation_failed path=%s problems=%s", request.url.path, problems
        )
        return JSONResponse(status_code=422, content={"detail": problems})

    application.include_router(tools_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
