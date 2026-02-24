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
        """Base URL of the frontend. Used to build links in emails: FRONTEND_URL + path + ?token=..."""
        return os.getenv("FRONTEND_URL", "http://localhost:3000")

    @property
    def EMAIL_VERIFY_PATH(self) -> str:
        """Frontend path for email verification. Link = FRONTEND_URL + EMAIL_VERIFY_PATH + ?token=..."""
        return os.getenv("EMAIL_VERIFY_PATH", "/verify-email")

    @property
    def PASSWORD_RESET_PATH(self) -> str:
        """Frontend path for password reset. Link = FRONTEND_URL + PASSWORD_RESET_PATH + ?token=..."""
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

    # Rate limit for endpoints that send email (register, verify-email/request, password/forgot)
    @property
    def RATE_LIMIT_EMAIL_REQUESTS(self) -> int:
        """Max requests per RATE_LIMIT_EMAIL_WINDOW_SECONDS per IP for email-sending endpoints."""
        return self._get_int("RATE_LIMIT_EMAIL_REQUESTS", 5)

    @property
    def RATE_LIMIT_EMAIL_WINDOW_SECONDS(self) -> int:
        """Time window in seconds for email rate limit (default 15 min)."""
        return self._get_int("RATE_LIMIT_EMAIL_WINDOW_SECONDS", 900)

    @property
    def RESEND_API_KEY(self) -> str:
        return os.getenv("RESEND_API_KEY", "").strip()

    @property
    def RESEND_FROM_EMAIL(self) -> str:
        """Sender for Resend: 'Name <email@domain.com>' or 'email@domain.com'."""
        return os.getenv("RESEND_FROM_EMAIL", "").strip()

    @property
    def RESEND_TEMPLATE_VERIFY_EMAIL(self) -> str:
        """Resend template id for email verification (registration)."""
        return os.getenv("RESEND_TEMPLATE_VERIFY_EMAIL", "").strip()

    @property
    def RESEND_TEMPLATE_PASSWORD_RESET(self) -> str:
        """Resend template id for password reset."""
        return os.getenv("RESEND_TEMPLATE_PASSWORD_RESET", "").strip()

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

    @property
    def RUN_MIGRATIONS_ON_STARTUP(self) -> bool:
        return self._get_bool("RUN_MIGRATIONS_ON_STARTUP", True)

    @property
    def RUN_SEED_ON_STARTUP(self) -> bool:
        return self._get_bool("RUN_SEED_ON_STARTUP", True)


settings = Settings()
