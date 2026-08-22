from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


def test_settings_reads_explicit_environment_values_as_expected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches configuration fields that do not load their documented environment values."""
    values = {
        "DATABASE_URL": "postgresql://user:password@db.example.test:5432/app",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
        "SUPABASE_STORAGE_BUCKET": "private-assets",
        "SUPABASE_RESUME_OBJECT_PATH": "documents/resume.pdf",
        "SUPABASE_ARCHITECTURE_OBJECT_PATH": "images/architecture.png",
        "WHAPI_BASE_URL": "https://whapi.example.test",
        "WHAPI_TOKEN": "whapi-token",
        "SARVAM_TOOL_SECRET": "tool-secret",
        "DEFAULT_TIMEZONE": "UTC",
        "CALLBACK_POLL_SECONDS": "30",
        "CALLBACK_SIGNED_URL_TTL_SECONDS": "1200",
        "DEVELOPER_NAME": "Test Developer",
        "DEVELOPER_PHONE": "+919999999999",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.database_url.get_secret_value() == values["DATABASE_URL"]
    assert settings.supabase_url == values["SUPABASE_URL"]
    assert settings.supabase_service_role_key.get_secret_value() == values["SUPABASE_SERVICE_ROLE_KEY"]
    assert settings.supabase_storage_bucket == values["SUPABASE_STORAGE_BUCKET"]
    assert settings.supabase_resume_object_path == values["SUPABASE_RESUME_OBJECT_PATH"]
    assert settings.supabase_architecture_object_path == values["SUPABASE_ARCHITECTURE_OBJECT_PATH"]
    assert settings.whapi_base_url == values["WHAPI_BASE_URL"]
    assert settings.whapi_token.get_secret_value() == values["WHAPI_TOKEN"]
    assert settings.sarvam_tool_secret.get_secret_value() == values["SARVAM_TOOL_SECRET"]
    assert settings.default_timezone == values["DEFAULT_TIMEZONE"]
    assert settings.callback_poll_seconds == 30
    assert settings.callback_signed_url_ttl_seconds == 1200
    assert settings.developer_name == values["DEVELOPER_NAME"]
    assert settings.developer_phone == values["DEVELOPER_PHONE"]
    assert isinstance(settings.database_url, SecretStr)
    assert isinstance(settings.supabase_service_role_key, SecretStr)
    assert isinstance(settings.whapi_token, SecretStr)
    assert isinstance(settings.sarvam_tool_secret, SecretStr)


@pytest.mark.asyncio
async def test_health_boots_without_integration_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches eager integration setup that makes the health endpoint unavailable."""
    for name in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "WHAPI_TOKEN",
        "SARVAM_TOOL_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    app = create_app(settings=Settings(_env_file=None))
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
