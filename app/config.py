from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: SecretStr = SecretStr("")
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_storage_bucket: str = "sales-agent-assets"
    supabase_resume_object_path: str = "resume/Nischal_Saxena_Resume.pdf"
    supabase_architecture_object_path: str = "architecture/voice-agent.png"
    whapi_base_url: str = "https://gate.whapi.cloud"
    whapi_token: SecretStr = SecretStr("")
    sarvam_tool_secret: SecretStr = SecretStr("")
    sarvam_api_base: str = "https://apps.sarvam.ai"
    sarvam_api_key: SecretStr = SecretStr("")
    sarvam_org_id: str = ""
    sarvam_workspace_id: str = ""
    sarvam_app_id: str = ""
    sarvam_app_version: str = ""
    sarvam_version_filter: str = ""
    sarvam_connection_id: str = ""
    sarvam_agent_phone_number: str = ""
    sarvam_callback_webhook_url: str = ""
    sarvam_initial_state_name: str = ""
    sarvam_callback_opening: str = ""
    default_timezone: str = "Asia/Kolkata"
    callback_poll_seconds: int = 15
    callback_signed_url_ttl_seconds: int = 900
    developer_name: str = "Nischal Saxena"
    developer_phone: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
