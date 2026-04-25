from datetime import datetime, timezone
from typing import Literal, Any

from pydantic import BaseModel, UUID1, Field


class Conversation(BaseModel):
    user_id: int
    conversation_id: UUID1
    title: str


class Message(BaseModel):
    conversation_id: UUID1 | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    role: Literal['user', 'assistant']
    type: Literal['tool_call_req', 'tool_call_resp', 'thinking', 'content'] = 'content'
    content: str


class MessageRequest(BaseModel):
    conversation_id: UUID1 | None = None
    content: str
    model: str
    web_access: bool = False


class AgentStreamChunk(BaseModel):
    type: Literal['metadata', 'tool_call_req', 'tool_call_resp', 'thinking', 'content', 'done', 'error', 'warning']
    conversation_id: UUID1 | None = None
    delta: str | None = None
    data: Any = None
    exception: str | None = None
    status_code: int = 200
    