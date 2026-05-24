from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────
    APP_NAME: str = "Red Rose Laundry API"
    APP_ENV: str = "development"
    SECRET_KEY: str = "changeme"
    API_PREFIX: str = "/api/v1"

    # ── Database ─────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/redrose_db"

    # ── M-Pesa Daraja ────────────────────────────────
    MPESA_ENV: str = "sandbox"
    MPESA_CONSUMER_KEY: str = ""
    MPESA_CONSUMER_SECRET: str = ""
    MPESA_SHORTCODE: str = "174379"
    MPESA_PASSKEY: str = ""
    MPESA_CALLBACK_URL: str = "https://yourdomain.com/api/v1/payments/mpesa/callback"

    @property
    def MPESA_BASE_URL(self) -> str:
        if self.MPESA_ENV == "production":
            return "https://api.safaricom.co.ke"
        return "https://sandbox.safaricom.co.ke"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
