import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SerializeAsAny


class Conversation(BaseModel):
    user_id: int
    conversation_id: uuid.UUID
    title: str


class FunctionToolCall(BaseModel):
    class Function(BaseModel):
        name: str
        arguments: str

    id: str
    function: Function


Role = Literal["user", "assistant", "tool"]


class BaseMessage(BaseModel):
    conversation_id: uuid.UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    role: Role
    content: str = ""


class UserMessage(BaseMessage):
    role: Role = "user"


class AssistantMessage(BaseMessage):
    role: Role = "assistant"
    reasoning: str | None = None
    tool_calls: SerializeAsAny[list[FunctionToolCall]] | None = None


class ToolMessage(BaseMessage):
    role: Role = "tool"
    tool_call_id: str


Message = UserMessage | AssistantMessage | ToolMessage


class MessageRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str
    model: str
    web_access: bool = False


class AgentStreamChunk(BaseModel):
    type: Literal[
        "metadata",
        "reasoning",
        "tool_calls",
        "tool",
        "content",
        "done",
        "error",
    ]
    conversation_id: uuid.UUID | None = None
    tool_call_id: str | None = None
    delta: str | None = None
    data: SerializeAsAny[list[FunctionToolCall] | str] | None = None
    exception: str | None = None
    status_code: int = 200
