from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionFactory


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session from the lazily configured application factory."""
    session_factory: AsyncSessionFactory | None = getattr(
        request.app.state, "session_factory", None
    )
    if session_factory is None:
        raise RuntimeError("database_not_configured")

    async with session_factory() as session:
        yield session


async def verify_tool_secret(request: Request) -> None:
    """Require the configured tool secret without revealing configuration state."""
    expected_secret = request.app.state.settings.sarvam_tool_secret.get_secret_value()
    provided_secret = request.headers.get("X-Tool-Secret", "")
    secret_matches = secrets.compare_digest(provided_secret, expected_secret)

    if not expected_secret or not provided_secret or not secret_matches:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
