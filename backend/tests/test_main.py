import json
import uuid
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.domain.models import (
    AgentStreamChunk,
    AssistantMessage,
    Conversation,
    FunctionToolCall,
    UserMessage,
)
from api.main import (
    DBClient,
    LLMClient,
    app,
    get_db,
    get_llm,
)
from fastapi.testclient import TestClient


def tokenize(text: str) -> list[str]:
    return [w if i == 0 else " " + w for i, w in enumerate(text.split())]


class MockLLMStreamer:
    def __init__(
        self,
        content: str = "",
        reasoning: str | None = None,
        tool_calls: list[FunctionToolCall] | None = None,
    ):
        self.chunks = []
        if reasoning:
            for token in tokenize(reasoning):
                self.chunks.append(AgentStreamChunk(type="reasoning", delta=token))
        if content:
            for token in tokenize(content):
                self.chunks.append(AgentStreamChunk(type="content", delta=token))
        msg = AssistantMessage(
            content=content, reasoning=reasoning, tool_calls=tool_calls
        )
        self.chunks.append(msg)

    async def stream_response(
        self, *args, **kwargs
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        for chunk in self.chunks:
            yield chunk


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block:
            continue
        assert block.startswith("data: ")
        payload = block.removeprefix("data: ")
        events.append(json.loads(payload))
    return events


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock(DBClient)


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock(LLMClient)
    llm.stream_response = MagicMock()  # Initialize as MagicMock for call tracking
    return llm


@pytest.fixture
def mock_tool_registry() -> dict:
    return {}


@pytest.fixture
def mock_is_disconnected() -> AsyncMock:
    return AsyncMock(return_value=False)


class TestAppEndpoints:
    @pytest.fixture
    def client(
        self,
        mock_db: AsyncMock,
        mock_llm: MagicMock,
        # mock_tool_registry: dict,
        # mock_is_disconnected: AsyncMock,
    ) -> Generator[TestClient, None, None]:
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_llm] = lambda: mock_llm
        # app.dependency_overrides[get_tool_registry] = lambda: mock_tool_registry
        # app.dependency_overrides[get_disconnect_checker] = lambda: mock_is_disconnected
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_list_models(self, client: TestClient, mock_llm: MagicMock):
        models = ["claude", "gemini", "gpt"]
        mock_llm.list_models.return_value = models

        response = client.get("/models")

        assert response.status_code == 200
        assert response.json() == models
        mock_llm.list_models.assert_awaited_once()

    def test_list_conversations(self, client: TestClient, mock_db: AsyncMock):
        mock_db.list_conversations.return_value = [
            Conversation(conversation_id=uuid.uuid1(), user_id=0, title="Conversation"),
            Conversation(
                conversation_id=uuid.uuid1(), user_id=0, title="Another conversation"
            ),
            Conversation(
                conversation_id=uuid.uuid1(),
                user_id=0,
                title="Yet another conversation",
            ),
        ]

        response = client.get("/conversations")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        assert [c["title"] for c in body] == [
            "Conversation",
            "Another conversation",
            "Yet another conversation",
        ]
        mock_db.list_conversations.assert_awaited_once_with(user_id=0)

    def test_list_messages(self, client: TestClient, mock_db: AsyncMock):
        conv_id = uuid.uuid1()
        mock_db.scroll_messages.return_value = [
            AssistantMessage(conversation_id=conv_id, content="Hi there!"),
            UserMessage(conversation_id=conv_id, content="Hello"),
        ]

        response = client.get(f"/conversations/{conv_id}/messages")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert [m["role"] for m in body] == ["assistant", "user"]
        assert [m["content"] for m in body] == ["Hi there!", "Hello"]

        assert mock_db.scroll_messages.await_count == 1
        assert mock_db.scroll_messages.await_args.kwargs["conversation_id"] == conv_id

    def test_delete_conversation(self, client: TestClient, mock_db: AsyncMock):
        conv_id = uuid.uuid1()

        response = client.delete(f"/conversations/{conv_id}")

        assert response.status_code == 200
        mock_db.delete_conversation.assert_awaited_once_with(
            user_id=0, conversation_id=conv_id
        )

    def test_rename_conversation(self, client: TestClient, mock_db: AsyncMock):
        conv_id = uuid.uuid1()
        new_title = "New Conversation Title"

        response = client.patch(f"/conversations/{conv_id}", json={"title": new_title})

        assert response.status_code == 200
        mock_db.rename_conversation.assert_awaited_once_with(
            user_id=0, conversation_id=conv_id, new_title=new_title
        )

    def test_health(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
