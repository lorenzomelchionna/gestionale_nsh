from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://nsh:nshpass@localhost:5432/new_style_hair"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "changeme"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = "noreply@newstylair.it"
    EMAILS_FROM_NAME: str = "New Style Hair"
    # Brevo HTTP API (preferred on hosts that block outbound SMTP, e.g. Railway).
    # When set, email is sent via HTTPS instead of SMTP.
    BREVO_API_KEY: str = ""

    # App
    APP_ENV: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"

    # Sentry (optional)
    SENTRY_DSN: Optional[str] = Field(default=None)

    # Twilio WhatsApp (optional — leave empty to disable)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = ""   # e.g. "whatsapp:+14155238886"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
