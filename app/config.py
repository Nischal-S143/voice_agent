from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: SecretStr = SecretStr("")
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_storage_bucket: str = "sales-agent-assets"
    supabase_resume_object_path: str = "resume/Parv_Agarwal_Resume.pdf"
    supabase_architecture_object_path: str = "architecture/voice-agent.png"
    whapi_base_url: str = "https://gate.whapi.cloud"
    whapi_token: SecretStr = SecretStr("")
    sarvam_tool_secret: SecretStr = SecretStr("")
    default_timezone: str = "Asia/Kolkata"
    callback_poll_seconds: int = 15
    callback_signed_url_ttl_seconds: int = 900
    developer_name: str = "Parv Agarwal"
    developer_phone: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
