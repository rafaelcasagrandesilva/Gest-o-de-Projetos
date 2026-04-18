from __future__ import annotations

from pydantic import Field, field_validator
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

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/sgp",
        alias="DATABASE_URL",
    )

    # Armazenamento local de PDFs das NFs (contas a receber); em produção prefira volume persistente.
    receivable_upload_dir: str = Field(default="var/receivable_uploads", alias="RECEIVABLE_UPLOAD_DIR")
    receivable_pdf_max_bytes: int = Field(default=10 * 1024 * 1024, alias="RECEIVABLE_PDF_MAX_BYTES")

    @field_validator("jwt_secret_key", "jwt_algorithm", mode="before")
    @classmethod
    def strip_secrets(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


settings = Settings()
