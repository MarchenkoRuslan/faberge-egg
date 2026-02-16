import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    @staticmethod
    def _get_int(name: str, default: int) -> int:
        return int(os.getenv(name, str(default)))

    @property
    def BASE_URL(self) -> str:
        return os.getenv("BASE_URL", "http://localhost:8000")

    @property
    def DATABASE_URL(self) -> str:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return database_url

    @property
    def JWT_SECRET(self) -> str:
        return os.getenv("JWT_SECRET", "change-me-in-production")

    @property
    def JWT_ALGORITHM(self) -> str:
        return os.getenv("JWT_ALGORITHM", "HS256")

    @property
    def JWT_EXPIRE_MINUTES(self) -> int:
        return self._get_int("JWT_EXPIRE_MINUTES", 60)

    @property
    def STRIPE_SECRET_KEY(self) -> str:
        return os.getenv("STRIPE_SECRET_KEY", "")

    @property
    def STRIPE_WEBHOOK_SECRET(self) -> str:
        return os.getenv("STRIPE_WEBHOOK_SECRET", "")

    @property
    def STRIPE_SUCCESS_URL(self) -> str:
        return os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/success")

    @property
    def STRIPE_CANCEL_URL(self) -> str:
        return os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/cancel")

    @property
    def PAYKILLA_API_KEY(self) -> str:
        return os.getenv("PAYKILLA_API_KEY", "")

    @property
    def PAYKILLA_WEBHOOK_SECRET(self) -> str:
        return os.getenv("PAYKILLA_WEBHOOK_SECRET", "")

    @property
    def PAYKILLA_SUCCESS_URL(self) -> str:
        return os.getenv("PAYKILLA_SUCCESS_URL", "http://localhost:3000/success")

    @property
    def PAYKILLA_CANCEL_URL(self) -> str:
        return os.getenv("PAYKILLA_CANCEL_URL", "http://localhost:3000/cancel")

    @property
    def MIN_FRACTIONS(self) -> int:
        return self._get_int("MIN_FRACTIONS", 1)

    @property
    def CORS_ORIGINS(self) -> str:
        return os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")


settings = Settings()

# Validate critical settings
if settings.JWT_SECRET == "change-me-in-production":
    import warnings
    warnings.warn("JWT_SECRET is using default value. Change it in production!", UserWarning)
