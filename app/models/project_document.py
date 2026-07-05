from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ProjectDocumentCategory(str, enum.Enum):
    CONTRATO = "CONTRATO"
    ADITIVO = "ADITIVO"
    CRONOGRAMA = "CRONOGRAMA"
    ART = "ART"
    MEMORIAL = "MEMORIAL"
    LICENCA = "LICENCA"
    OUTRO = "OUTRO"


class ProjectDocument(TimestampUUIDMixin, Base):
    """Documento anexado a um projeto (relação 1-N).

    Cadastral/documental: não participa de nenhuma regra financeira, dashboard ou
    indicador. O arquivo em si é gravado em disco (mesmo mecanismo dos anexos de
    ativos); aqui persistimos apenas o caminho (`storage_path`).
    """

    __tablename__ = "project_documents"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[ProjectDocumentCategory] = mapped_column(
        SAEnum(ProjectDocumentCategory, name="project_document_category"),
        nullable=False,
        default=ProjectDocumentCategory.OUTRO,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)

    project: Mapped["Project"] = relationship(back_populates="documents")  # noqa: F821
