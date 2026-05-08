from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    env: str = Field(default="local", alias="ENV")
    app_name: str = Field(default="SGP Backend", alias="APP_NAME")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # True = prints no console (token/payload/user_id) para depuração local
    auth_debug: bool = Field(default=False, alias="AUTH_DEBUG")

    # Produção: lista separada por vírgula (ex.: https://app.exemplo.com,https://www.exemplo.com).
    # Em ENV=local/dev/test, se vazio, usa localhost do Vite por padrão.
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    # E-mails com privilégios de superusuário operacional (emergência). Se vazio, usa lista interna legada.
    app_superuser_emails: str = Field(default="", alias="APP_SUPERUSER_EMAILS")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/sgp",
        alias="DATABASE_URL",
    )
    db_pool_size: int = Field(default=5, ge=1, le=50, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=15, ge=0, le=100, alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=1800, ge=300, alias="DB_POOL_RECYCLE_SECONDS")

    # Armazenamento local de PDFs das NFs (contas a receber); em produção prefira volume persistente.
    receivable_upload_dir: str = Field(default="var/receivable_uploads", alias="RECEIVABLE_UPLOAD_DIR")
    receivable_pdf_max_bytes: int = Field(default=5 * 1024 * 1024, alias="RECEIVABLE_PDF_MAX_BYTES")

    @field_validator("jwt_secret_key", "jwt_algorithm", mode="before")
    @classmethod
    def strip_secrets(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @staticmethod
    def _is_production_env(env: str) -> bool:
        return (env or "").strip().lower() in ("production", "prod", "live")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self._is_production_env(self.env):
            weak = {"change-me", "secret", "changeme"}
            key = (self.jwt_secret_key or "").strip()
            if len(key) < 32 or key.lower() in weak:
                raise ValueError(
                    "Em produção (ENV=production), defina JWT_SECRET_KEY com pelo menos 32 caracteres aleatórios."
                )
            if self.auth_debug:
                raise ValueError("Em produção, AUTH_DEBUG deve ser false.")
        return self

    def resolved_cors_origins(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if raw:
            return [x.strip() for x in raw.split(",") if x.strip()]
        if (self.env or "").lower() in ("local", "development", "dev", "test"):
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        raise ValueError(
            "Defina CORS_ORIGINS no .env com os domínios HTTPS do frontend (ex.: https://app.seudominio.com)."
        )

    def is_production(self) -> bool:
        return self._is_production_env(self.env)


settings = Settings()
