from __future__ import annotations

import asyncio
from typing import Any


class StorageServiceError(RuntimeError):
    """Sanitized private-storage failure."""


class StorageService:
    def __init__(self, client: Any, bucket: str, ttl_seconds: int) -> None:
        self._client = client
        self._bucket = bucket
        self._ttl_seconds = ttl_seconds

    async def create_signed_url(self, object_path: str) -> str:
        try:
            response = await asyncio.to_thread(
                self._client.storage.from_(self._bucket).create_signed_url,
                object_path,
                self._ttl_seconds,
            )
        except Exception:
            raise StorageServiceError("storage_signed_url_failed") from None
        if not isinstance(response, dict):
            raise StorageServiceError("storage_signed_url_failed")
        url = response.get("signedURL") or response.get("signedUrl")
        if not isinstance(url, str) or not url:
            raise StorageServiceError("storage_signed_url_failed")
        return url
