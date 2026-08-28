from __future__ import annotations

from pathlib import Path

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

    # Raiz única de todo upload em disco. Em produção aponte para o volume persistente
    # (ex.: STORAGE_ROOT=/data): os diretórios abaixo passam a ser derivados dela, então
    # qualquer novo campo de upload nasce no volume sem depender de mais uma variável.
    storage_root: str | None = Field(default=None, alias="STORAGE_ROOT")

    # Armazenamento local de PDFs das NFs (contas a receber); em produção prefira volume persistente.
    receivable_upload_dir: str = Field(default="var/receivable_uploads", alias="RECEIVABLE_UPLOAD_DIR")
    receivable_pdf_max_bytes: int = Field(default=5 * 1024 * 1024, alias="RECEIVABLE_PDF_MAX_BYTES")

    asset_upload_dir: str = Field(default="var/asset_uploads", alias="ASSET_UPLOAD_DIR")
    asset_upload_max_bytes: int = Field(default=15 * 1024 * 1024, alias="ASSET_UPLOAD_MAX_BYTES")

    # Documentos de projeto (mesmo mecanismo de disco dos anexos de ativos).
    project_document_dir: str = Field(default="var/project_documents", alias="PROJECT_DOCUMENT_DIR")
    project_document_max_bytes: int = Field(default=25 * 1024 * 1024, alias="PROJECT_DOCUMENT_MAX_BYTES")

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

    @model_validator(mode="after")
    def align_storage_dirs(self) -> "Settings":
        """Mantém todo upload em disco na mesma raiz dos PDFs de NF.

        Em produção só `RECEIVABLE_UPLOAD_DIR` apontava para o volume persistente;
        anexos de ativos e documentos de projeto ficavam no default relativo, dentro
        do container efêmero, e sumiam a cada redeploy. Aqui os diretórios que NÃO
        foram definidos explicitamente por variável de ambiente passam a derivar da
        raiz — `STORAGE_ROOT` quando existir, senão a pasta que contém o diretório
        das NFs. Quem define a variável continua no controle, e o diretório das NFs
        nunca é reescrito (não mexe no que já funciona).
        """
        root = self.resolved_storage_root()
        if root is None:
            return self
        derived = {
            # Só entram aqui os diretórios sem variável própria definida; por isso o
            # das NFs é derivado apenas quando STORAGE_ROOT é quem define a raiz.
            "receivable_upload_dir": "receivable_uploads",
            "asset_upload_dir": "asset_uploads",
            "project_document_dir": "project_documents",
        }
        for field, subdir in derived.items():
            if field not in self.model_fields_set:
                object.__setattr__(self, field, str(root / subdir))
        return self

    def resolved_storage_root(self) -> Path | None:
        """Raiz de armazenamento, ou None quando não há como derivá-la."""
        raw = (self.storage_root or "").strip()
        if raw:
            return Path(raw)
        if "receivable_upload_dir" not in self.model_fields_set:
            return None  # ambiente sem configuração: preserva os defaults relativos
        nf_dir = Path(self.receivable_upload_dir)
        parent = nf_dir.parent
        # RECEIVABLE_UPLOAD_DIR=/data → a própria pasta é a raiz (o pai seria "/").
        return nf_dir if parent in (Path("/"), Path(".")) else parent

    def storage_dirs(self) -> dict[str, Path]:
        """Diretórios de upload em uso, para log/diagnóstico no startup."""
        return {
            "RECEIVABLE_UPLOAD_DIR": Path(self.receivable_upload_dir),
            "ASSET_UPLOAD_DIR": Path(self.asset_upload_dir),
            "PROJECT_DOCUMENT_DIR": Path(self.project_document_dir),
        }

    def is_production(self) -> bool:
        return self._is_production_env(self.env)


settings = Settings()
