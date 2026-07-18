from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    mfa_secret: Optional[str] = None
    mfa_enabled: bool = False
    role: str = Field(default="user")
    theme: str = Field(default="dark")
    piece_set: str = Field(default="cburnett")
    board_theme: str = Field(default="brown")
    sounds_on: bool = True
    tts_enabled: bool = True
    tts_voice: str = Field(default="Microsoft Zira")
    boost_visibility: bool = False
    is_verified: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
