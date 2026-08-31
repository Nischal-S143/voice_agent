from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.utils.phone import normalize_indian_phone

logger = logging.getLogger(__name__)


class WhapiProviderError(RuntimeError):
    """A sanitized Whapi failure safe to handle outside this module."""


@dataclass(frozen=True, slots=True)
class WhapiResult:
    message_id: str
    success: bool = True


class WhapiService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: str,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._token = token

    async def send_text(self, phone: str, text: str) -> WhapiResult:
        return await self._send(
            "/messages/text",
            {"to": normalize_indian_phone(phone), "body": text},
            "send_text",
        )

    async def send_image(
        self, phone: str, image: str, caption: str | None = None
    ) -> WhapiResult:
        payload: dict[str, Any] = {
            "to": normalize_indian_phone(phone),
            "media": image,
        }
        if caption:
            payload["caption"] = caption
        return await self._send("/messages/image", payload, "send_image")

    async def send_document(
        self,
        phone: str,
        document: str,
        filename: str | None = None,
        caption: str | None = None,
    ) -> WhapiResult:
        payload: dict[str, Any] = {
            "to": normalize_indian_phone(phone),
            "media": document,
        }
        if filename:
            payload["filename"] = filename
        if caption:
            payload["caption"] = caption
        return await self._send("/messages/document", payload, "send_document")

    async def _send(
        self, endpoint: str, payload: dict[str, Any], operation: str
    ) -> WhapiResult:
        if not self._token:
            raise WhapiProviderError("whapi_not_configured")
        try:
            response = await self._client.post(
                f"{self._base_url}{endpoint}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(10.0, connect=3.0),
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.error(
                "whapi_request_failed",
                extra={
                    "phone": payload.get("to"),
                    "operation": operation,
                    "status": "failed",
                    "error": type(error).__name__,
                },
            )
            raise WhapiProviderError("whapi_request_failed") from None

        message_id = _extract_message_id(data)
        if message_id is None:
            logger.error(
                "whapi_invalid_response",
                extra={
                    "phone": payload.get("to"),
                    "operation": operation,
                    "status": "failed",
                    "error": "missing_message_id",
                },
            )
            raise WhapiProviderError("whapi_invalid_response")

        logger.info(
            "whapi_message_sent",
            extra={
                "phone": payload.get("to"),
                "operation": operation,
                "status": "success",
                "provider_message_id": message_id,
            },
        )
        return WhapiResult(message_id=message_id)


def _extract_message_id(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("id"), str):
        return data["id"]
    message = data.get("message")
    if isinstance(message, dict) and isinstance(message.get("id"), str):
        return message["id"]
    messages = data.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict) and isinstance(first.get("id"), str):
            return first["id"]
    return None
