from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Technula EduFlow"

    # ── DATABASE ──────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/insights_db"
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "insights_ai"

    # ── AI (Gemini) ───────────────────────────
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # ── AUTH / JWT ─────────────────────────────
    JWT_SECRET_KEY: str = "change-this-in-production-super-secret-key-2024"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # ── EMAIL (Resend) ────────────────────────
    RESEND_API_KEY: str | None = None
    RESEND_FROM_EMAIL: str | None = "classes@mail.technula.com"
    RESEND_FROM_NAME: str | None = "Technula Team"
    RESEND_API_URL: str = "https://api.resend.com"
    RESEND_TIMEOUT_SECONDS: int = 20
    EMAIL_FROM: str = "Technula Team <classes@mail.technula.com>"

    # ── WHATSAPP (Cloud API) ──────────────────
    WHATSAPP_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v18.0"

    # ── FIREBASE (FCM) ────────────────────────
    FIREBASE_CREDENTIALS_JSON: str | None = None  # Path to service account JSON

    # ── CORS ──────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:8087",
        "https://eduflow.technula.com",
        "https://technulaeduflow.technula.com",
        "*"
    ]

    # ── MULTI-TENANT PAYMENT ENCRYPTION (SCHOOL FEE CREDENTIALS) ─────────
    PAYMENT_ENCRYPTION_KEY: str = "school-os-aes256-secret-encryption-key-32b!"

    # ── PAYU INDIA (SAAS PLATFORM SUBSCRIPTIONS) ─────────────────────────
    PAYU_KEY: str | None = None
    PAYU_MERCHANT_KEY: str | None = None
    PAYU_SALT: str | None = None
    PAYU_MERCHANT_SALT: str | None = None
    PAYU_ENV: str = "live"
    PAYU_MODE: str | None = None
    PAYU_SUCCESS_URL: str | None = "https://insights.agpkacademy.in/api/subscription/payu-callback/success"
    PAYU_FAIL_URL: str | None = "https://insights.agpkacademy.in/api/subscription/payu-callback/fail"
    PAYU_SUCCESS_URL_LOCAL: str | None = "http://localhost:8000/subscription/payu-callback/success"
    PAYU_FAIL_URL_LOCAL: str | None = "http://localhost:8000/subscription/payu-callback/fail"

    @property
    def effective_payu_key(self) -> str:
        return self.PAYU_KEY or self.PAYU_MERCHANT_KEY or ""

    @property
    def effective_payu_salt(self) -> str:
        return self.PAYU_SALT or self.PAYU_MERCHANT_SALT or ""

    @property
    def effective_payu_mode(self) -> str:
        mode = self.PAYU_ENV or self.PAYU_MODE or "live"
        return "live" if mode.lower() == "live" else "test"

    # ── DLT SMS GATEWAY (AGPK ACADEMY / META REACH) ───────────────────────
    METAREACH_API_KEY: str | None = None
    METAREACH_SENDER_ID: str | None = "AGPKAC"
    METAREACH_TEMPLATE_ID: str | None = "1707177071739047190"
    SMS_API_URL: str = "https://sms.metareach.in/vb/apikey.php"
    SMS_API_KEY: str | None = None
    SMS_SENDER_ID: str | None = "AGPKAC"
    SMS_PE_ID: str | None = None
    SMS_TE_ID: str | None = "1707177071739047190"

    @property
    def effective_sms_api_key(self) -> str:
        return (self.METAREACH_API_KEY or self.SMS_API_KEY or "").strip()

    @property
    def effective_sms_sender_id(self) -> str:
        return (self.METAREACH_SENDER_ID or self.SMS_SENDER_ID or "AGPKAC").strip()

    @property
    def effective_sms_template_id(self) -> str:
        return (self.METAREACH_TEMPLATE_ID or self.SMS_TE_ID or "1707177071739047190").strip()

    # ── APP ───────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"

    # ── CLOUDFLARE R2 / AWS S3 STORAGE ─────────────────────────
    S3_ENDPOINT_URL: str | None = None
    AWS_S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    S3_BUCKET_NAME: str | None = None
    AWS_S3_BUCKET_NAME: str | None = None
    AWS_REGION: str = "auto"
    R2_PUBLIC_URL_PREFIX: str | None = None
    AUTO_APPROVE_WFH_DEVICES: bool = False

    @property
    def effective_s3_endpoint_url(self) -> str | None:
        return self.S3_ENDPOINT_URL or self.AWS_S3_ENDPOINT_URL or None

    @property
    def effective_s3_access_key(self) -> str | None:
        return self.S3_ACCESS_KEY_ID or self.AWS_ACCESS_KEY_ID or None

    @property
    def effective_s3_secret_key(self) -> str | None:
        return self.S3_SECRET_ACCESS_KEY or self.AWS_SECRET_ACCESS_KEY or None

    @property
    def effective_s3_bucket(self) -> str | None:
        return self.S3_BUCKET_NAME or self.AWS_S3_BUCKET_NAME or None

    # ── SUPERADMIN SAAS CONFIG ─────────────────
    SUPERADMIN_PHONES: str = ""

    @property
    def authorized_superadmin_phones(self) -> set[str]:
        raw = self.SUPERADMIN_PHONES or ""
        return {"".join(c for c in p if c.isdigit())[-10:] for p in raw.split(",") if p.strip()}

    class Config:
        import os
        from pathlib import Path
        _base = Path(__file__).resolve().parent.parent
        _env = _base / ".env"
        env_file = str(_env) if _env.exists() else ".env"
        case_sensitive = True
        extra = "ignore"



settings = Settings()
