from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class VideoLinkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=500)

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class VideoLinkResponse(BaseModel):
    id: UUID
    library_id: UUID
    title: str
    url: str
    created_at: datetime
