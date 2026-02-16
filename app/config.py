import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./marketplace.db")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_SUCCESS_URL: str = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/success")
    STRIPE_CANCEL_URL: str = os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/cancel")
    PAYKILLA_API_KEY: str = os.getenv("PAYKILLA_API_KEY", "")
    PAYKILLA_WEBHOOK_SECRET: str = os.getenv("PAYKILLA_WEBHOOK_SECRET", "")
    PAYKILLA_SUCCESS_URL: str = os.getenv("PAYKILLA_SUCCESS_URL", "http://localhost:3000/success")
    PAYKILLA_CANCEL_URL: str = os.getenv("PAYKILLA_CANCEL_URL", "http://localhost:3000/cancel")
    MIN_FRACTIONS: int = int(os.getenv("MIN_FRACTIONS", "1"))
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")


settings = Settings()

# Validate critical settings
if settings.JWT_SECRET == "change-me-in-production":
    import warnings
    warnings.warn("JWT_SECRET is using default value. Change it in production!", UserWarning)
