from enum import StrEnum
from datetime import datetime, timezone

from pydantic import BaseModel, UUID1, Field


class Conversation(BaseModel):
    user_id: int
    conversation_id: UUID1
    title: str


class Role(StrEnum):
    USER = 'user'
    ASSISTANT = 'assistant'


class Message(BaseModel):
    conversation_id: UUID1 | None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    role: Role
    content: str


class ReasoningEffort(StrEnum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class MessageRequest(BaseModel):
    conversation_id: UUID1 | None = None
    content: str
    model: str
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    