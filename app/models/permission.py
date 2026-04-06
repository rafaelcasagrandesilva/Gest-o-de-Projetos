from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class Permission(TimestampUUIDMixin, Base):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)

    user_links: Mapped[list["UserPermission"]] = relationship(back_populates="permission", cascade="all, delete-orphan")


class UserPermission(TimestampUUIDMixin, Base):
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),)

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    permission_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="user_permissions")
    permission: Mapped["Permission"] = relationship(back_populates="user_links")
