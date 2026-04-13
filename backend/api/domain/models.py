from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, UUID1, Field


class Conversation(BaseModel):
    user_id: int
    conversation_id: UUID1
    title: str


class Role(str, Enum):
    USER = 'user'
    ASSISTANT = 'assistant'
    SYSTEM = 'system'


class Message(BaseModel):
    conversation_id: UUID1 | None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    role: Role
    content: str
    