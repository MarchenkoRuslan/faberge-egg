import os


class Settings:
    @staticmethod
    def _get_int(name: str, default: int) -> int:
        return int(os.getenv(name, str(default)))

    @staticmethod
    def _get_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @property
    def BASE_URL(self) -> str:
        return os.getenv("BASE_URL", "http://localhost:8000")

    @property
    def FRONTEND_URL(self) -> str:
        return os.getenv("FRONTEND_URL", "http://localhost:3000")

    @property
    def EMAIL_VERIFY_PATH(self) -> str:
        return os.getenv("EMAIL_VERIFY_PATH", "/verify-email")

    @property
    def PASSWORD_RESET_PATH(self) -> str:
        return os.getenv("PASSWORD_RESET_PATH", "/restore-password")

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
    def JWT_REFRESH_EXPIRE_DAYS(self) -> int:
        return self._get_int("JWT_REFRESH_EXPIRE_DAYS", 30)

    @property
    def EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES(self) -> int:
        return self._get_int("EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES", 60 * 24)

    @property
    def PASSWORD_RESET_TOKEN_EXPIRE_MINUTES(self) -> int:
        return self._get_int("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", 30)

    @property
    def EMAIL_RESEND_COOLDOWN_SECONDS(self) -> int:
        return self._get_int("EMAIL_RESEND_COOLDOWN_SECONDS", 60)

    @property
    def SMTP_HOST(self) -> str:
        return os.getenv("SMTP_HOST", "").strip()

    @property
    def SMTP_PORT(self) -> int:
        return self._get_int("SMTP_PORT", 587)

    @property
    def SMTP_USER(self) -> str:
        return os.getenv("SMTP_USER", "").strip()

    @property
    def SMTP_PASSWORD(self) -> str:
        return os.getenv("SMTP_PASSWORD", "").strip()

    @property
    def SMTP_FROM_EMAIL(self) -> str:
        return os.getenv("SMTP_FROM_EMAIL", "").strip()

    @property
    def SMTP_FROM_NAME(self) -> str:
        return os.getenv("SMTP_FROM_NAME", "Marketplace API").strip()

    @property
    def SMTP_USE_TLS(self) -> bool:
        return self._get_bool("SMTP_USE_TLS", True)

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

    @property
    def DB_CONNECT_RETRIES(self) -> int:
        return self._get_int("DB_CONNECT_RETRIES", 10)

    @property
    def DB_CONNECT_RETRY_DELAY_SECONDS(self) -> int:
        return self._get_int("DB_CONNECT_RETRY_DELAY_SECONDS", 1)


settings = Settings()
