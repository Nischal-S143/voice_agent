from __future__ import annotations

import re
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel


class OutboundCallRequest(BaseModel):
    callback_id: int
    phone: str
    context: dict[str, object]


class OutboundCallResult(BaseModel):
    success: bool
    call_id: str | None = None
    provider_attempt_id: str | None = None
    error: str | None = None
    retryable: bool = False


class SarvamOutboundCaller(Protocol):
    async def place_call(self, request: OutboundCallRequest) -> OutboundCallResult: ...


class UnconfiguredSarvamOutboundCaller:
    async def place_call(self, request: OutboundCallRequest) -> OutboundCallResult:
        return OutboundCallResult(
            success=False,
            error="sarvam_outbound_not_configured",
            retryable=False,
        )


def _outbound_url(base: str, org_id: str, workspace_id: str) -> str:
    return (
        f"{base.rstrip('/')}/api/outbounds/v1"
        f"/orgs/{org_id}/workspaces/{workspace_id}/outbounds"
    )


def _app_version(raw: str) -> int | None:
    """Sarvam labels versions "v1" but the API only accepts the integer."""
    digits = re.sub(r"[^0-9]", "", raw or "")
    return int(digits) if digits else None


def _version_config(settings: Any) -> dict[str, object]:
    """Pin a published version when one is known, else ask for the latest.

    Sarvam rejects the call with "app_version is required when version_filter
    is specific", so the two fields have to be chosen together.
    """
    version = _app_version(settings.sarvam_app_version)
    override = (settings.sarvam_version_filter or "").strip()
    if version is not None:
        return {"version_filter": override or "specific", "app_version": version}
    return {"version_filter": override or "latest"}


def _as_variable(value: object) -> str | None:
    """Flatten a context value into the string form agent_variables expects."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value if item is not None]
        return ", ".join(parts) or None
    text = str(value).strip()
    return text or None


def _extract_call_id(body: object) -> str | None:
    """Pull the provider call id out of the Create Instant Outbound Call response.

    Sarvam returns ``attempt_id``; the remaining keys are defensive fallbacks.
    """
    if not isinstance(body, dict):
        return None
    for container in (body, body.get("data"), body.get("outbound")):
        if not isinstance(container, dict):
            continue
        for key in (
            "attempt_id",
            "attemptId",
            "call_id",
            "outbound_id",
            "id",
            "callId",
            "outboundId",
        ):
            value = container.get(key)
            if isinstance(value, str) and value:
                return value
    return None


class SarvamHttpOutboundCaller:
    """Place a single outbound call through the Sarvam Instant Outbound API."""

    def __init__(self, client: Any, settings: Any) -> None:
        self._client = client
        self._settings = settings

    async def place_call(self, request: OutboundCallRequest) -> OutboundCallResult:
        settings = self._settings
        # The agent reads call_id and phone from its input variables and echoes
        # them into every tool call. Sarvam's own id is not known until the
        # response, so mint one here and use it on both sides.
        call_id = f"cb-{request.callback_id}-{uuid4().hex[:12]}"
        app_config: dict[str, object] = {
            "app_id": settings.sarvam_app_id,
            "app_type": "agent",
            "connection_config": {
                "connection_id": settings.sarvam_connection_id,
                "agent_phone_number": settings.sarvam_agent_phone_number,
            },
            "agent_variables": self._agent_variables(request, call_id),
        }
        app_config.update(_version_config(settings))

        overrides = self._app_overrides(request, call_id)
        if overrides:
            app_config["app_overrides"] = overrides

        payload: dict[str, object] = {
            "app_config": app_config,
            "user_config": {"user_phone_number": _e164(request.phone)},
        }
        if settings.sarvam_callback_webhook_url:
            payload["webhook_config"] = {
                "url": settings.sarvam_callback_webhook_url,
                "metadata": {"callback_id": str(request.callback_id)},
            }

        try:
            response = await self._client.post(
                _outbound_url(
                    settings.sarvam_api_base,
                    settings.sarvam_org_id,
                    settings.sarvam_workspace_id,
                ),
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.sarvam_api_key.get_secret_value(),
                },
                json=payload,
                timeout=30.0,
            )
        except Exception:
            return OutboundCallResult(
                success=False, error="sarvam_outbound_unreachable", retryable=True
            )

        if response.status_code >= 500 or response.status_code == 429:
            return OutboundCallResult(
                success=False, error="sarvam_outbound_unavailable", retryable=True
            )
        if response.status_code == 402:
            # Credits can be topped up, so the callback must stay eligible rather
            # than being written off as a permanent failure.
            return OutboundCallResult(
                success=False,
                error="sarvam_outbound_insufficient_balance",
                retryable=True,
            )
        if response.status_code >= 400:
            return OutboundCallResult(
                success=False, error="sarvam_outbound_rejected", retryable=False
            )

        try:
            body = response.json()
        except ValueError:
            body = None
        attempt_id = _extract_call_id(body)
        if not attempt_id:
            return OutboundCallResult(
                success=False, error="sarvam_outbound_no_call_id", retryable=False
            )
        return OutboundCallResult(
            success=True, call_id=call_id, provider_attempt_id=attempt_id
        )

    def _agent_variables(
        self, request: OutboundCallRequest, call_id: str
    ) -> dict[str, str]:
        variables: dict[str, str] = {}
        for key, value in request.context.items():
            flattened = _as_variable(value)
            if flattened is not None:
                variables[key] = flattened
        variables["callback_id"] = str(request.callback_id)
        variables["call_id"] = call_id
        variables["phone"] = _e164(request.phone)
        return variables

    def _app_overrides(
        self, request: OutboundCallRequest, call_id: str
    ) -> dict[str, str]:
        overrides: dict[str, str] = {}
        template = self._settings.sarvam_callback_opening
        if template:
            try:
                overrides["initial_bot_message"] = template.format(
                    **self._agent_variables(request, call_id)
                )
            except (KeyError, IndexError):
                overrides["initial_bot_message"] = template
        if self._settings.sarvam_initial_state_name:
            overrides["initial_state_name"] = self._settings.sarvam_initial_state_name
        return overrides


def _e164(phone: str) -> str:
    compact = phone.strip()
    return compact if compact.startswith("+") else f"+{compact}"
