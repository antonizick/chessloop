from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class SystemSettings(SQLModel, table=True):
    """Singleton row for admin-configurable, runtime-editable system toggles."""

    __tablename__ = "system_settings"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    enforce_email_verification: bool = Field(default=True)
