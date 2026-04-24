from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, UUID1, Field


class Conversation(BaseModel):
    user_id: int
    conversation_id: UUID1
    title: str


class Message(BaseModel):
    conversation_id: UUID1 | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    role: Literal['user', 'assistant']
    type: Literal['tool_call_request', 'tool_call_response', 'thinking', 'content'] = 'content'
    content: str


class MessageRequest(BaseModel):
    conversation_id: UUID1 | None = None
    content: str
    model: str
    web_access: bool = False


class AgentStreamChunk(BaseModel):
    type: Literal['tool_call_request', 'tool_call_response', 'thinking', 'content', 'done']
    delta: str | None = None
    data: BaseModel | None = None
    