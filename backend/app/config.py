from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from functools import lru_cache
from typing import Optional

# Values that only exist so `python seed.py` works on a laptop with no .env.
# This repository is public, so they are not weak secrets — they are published
# ones, and the guard below refuses to boot with them anywhere but development.
_DEV_ONLY_SECRETS = {"changeme", "change_me_in_production", "secret", "test"}
MIN_SECRET_KEY_LENGTH = 32


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

    # Log (vedi app/logging_config.py). `INFO` scrive una riga per richiesta,
    # che a questi volumi sono poche migliaia al giorno; `WARNING` tiene solo
    # errori ed eventi di sicurezza. Sotto `INFO` la traccia degli accessi non
    # c'è più, ed è quella la ragione per cui i log esistono.
    LOG_LEVEL: str = "INFO"

    # Limiti di frequenza sugli endpoint pubblici (vedi app/rate_limit.py).
    # Spegnibile per i test, che fanno decine di login di fila di proposito.
    RATE_LIMIT_ENABLED: bool = True
    # Vuoto = usa REDIS_URL. I test lo puntano su `memory://`, perché la CI
    # ha solo Postgres e un Redis assente farebbe fallire i test sbagliati.
    RATE_LIMIT_STORAGE_URI: str = ""
    FRONTEND_URL: str = "http://localhost:5173"

    # Sentry (optional)
    SENTRY_DSN: Optional[str] = Field(default=None)

    # Twilio WhatsApp (optional — leave empty to disable)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = ""   # e.g. "whatsapp:+14155238886"

    # Template WhatsApp approvati da Meta, uno per tipo di messaggio.
    #
    # Servono per i messaggi che **il salone manda per primo**: fuori dalla
    # finestra di 24 ore da un messaggio della cliente, WhatsApp accetta solo
    # testo che Meta ha già approvato, e rifiuta il testo libero (errore
    # 63016). Le risposte dalla pagina Chat non passano di qui — quelle sono
    # dentro la finestra per definizione, visto che esistono perché la cliente
    # ha scritto.
    #
    # Vuote finché Meta non approva: in quel caso si continua a mandare testo
    # libero, che è ciò che serve per provare in Sandbox. Non è un ripiego per
    # la produzione — lì senza template il messaggio non parte e basta.
    TWILIO_TEMPLATE_CONFERMA: str = ""
    TWILIO_TEMPLATE_PROMEMORIA: str = ""
    TWILIO_TEMPLATE_COMPLEANNO: str = ""
    TWILIO_TEMPLATE_RESET_PASSWORD: str = ""

    @model_validator(mode="after")
    def _refuse_published_secrets_outside_development(self) -> "Settings":
        """Fail to start rather than run on a key anyone can read on GitHub.

        SECRET_KEY signs the tokens of admins, collaborators and clients alike,
        so booting with the default is not a weak configuration, it is an open
        door: anyone can mint themselves an admin token. The failure this
        guards against is silent — a variable lost while recreating a service,
        a typo in a rename — and the deploy is automatic, so nobody is watching
        at the moment it would happen.
        """
        if self.APP_ENV == "development":
            return self
        if self.SECRET_KEY in _DEV_ONLY_SECRETS:
            raise ValueError(
                f"SECRET_KEY è ancora il valore di sviluppo con APP_ENV={self.APP_ENV}. "
                "Questo repository è pubblico: quella chiave la conoscono tutti. "
                "Imposta una chiave vera prima di avviare."
            )
        if len(self.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY è lunga {len(self.SECRET_KEY)} caratteri, "
                f"il minimo è {MIN_SECRET_KEY_LENGTH}. Generane una con "
                "`python -c \"import secrets; print(secrets.token_hex(32))\"`."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
