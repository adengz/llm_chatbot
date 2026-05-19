import json
import random
import uuid
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.domain.models import (
    AgentStreamChunk,
    AssistantMessage,
    Conversation,
    FunctionToolCall,
    ToolMessage,
    UserMessage,
)
from api.infra.exceptions import LLMStreamingError, ToolExecutionError
from api.infra.tools import WebScrapeRequest, WebSearchRequest
from api.main import (
    SSE_PREFIX,
    SSE_SUFFIX,
    DBClient,
    FunctionToolSpec,
    LLMClient,
    LLMToolError,
    app,
    generate_stream,
    get_db,
    get_disconnect_checker,
    get_llm,
    get_tool_registry,
    handle_llm_stream,
    handle_tool_calls,
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


def parse_single_sse_event(event: str) -> dict:
    assert event.startswith(SSE_PREFIX)
    payload = event.removeprefix(SSE_PREFIX).removesuffix(SSE_SUFFIX)
    return json.loads(payload)


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block:
            continue
        events.append(parse_single_sse_event(block))
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


async def empty_stream() -> AsyncGenerator[str, None]:
    yield ""


class TestLLMStreamHandler:
    @pytest.fixture
    def streamer(self) -> MockLLMStreamer:
        return MockLLMStreamer(
            content="Hello! How can I help you today?", reasoning="Need a greeting."
        )

    @pytest.mark.asyncio
    async def test_handle_llm_stream_not_disconnected(
        self,
        mock_llm: MagicMock,
        mock_is_disconnected: AsyncMock,
        streamer: MockLLMStreamer,
    ):
        mock_llm.stream_response.side_effect = streamer.stream_response

        event, count = None, 0
        async for event, disconnected in handle_llm_stream(
            context=[],
            model="",
            web_access=False,
            llm=mock_llm,
            is_disconnected=mock_is_disconnected,
        ):
            count += 1
            assert not disconnected

        assert isinstance(event, AssistantMessage)
        assert event == streamer.chunks[-1]
        assert count == len(streamer.chunks)

    @pytest.mark.asyncio
    async def test_handle_llm_stream_disconnected_immediately(
        self,
        mock_llm: MagicMock,
        mock_is_disconnected: AsyncMock,
        streamer: MockLLMStreamer,
    ):
        mock_llm.stream_response.side_effect = streamer.stream_response
        mock_is_disconnected.side_effect = [True]

        event, disconnected = None, False
        async for event, disconnected in handle_llm_stream(
            context=[],
            model="",
            web_access=False,
            llm=mock_llm,
            is_disconnected=mock_is_disconnected,
        ):
            assert disconnected

        assert event is None

    @pytest.mark.asyncio
    async def test_handle_llm_stream_disconnected_in_middle(
        self,
        mock_llm: MagicMock,
        mock_is_disconnected: AsyncMock,
        streamer: MockLLMStreamer,
    ):
        streamed_tokens = random.randrange(1, len(streamer.chunks))
        mock_llm.stream_response.side_effect = streamer.stream_response
        mock_is_disconnected.side_effect = [False] * streamed_tokens + [True]

        event, disconnected = None, False
        async for event, disconnected in handle_llm_stream(
            context=[],
            model="",
            web_access=False,
            llm=mock_llm,
            is_disconnected=mock_is_disconnected,
        ):
            pass
        assert disconnected

        assert isinstance(event, AssistantMessage)
        full_msg = streamer.chunks[-1]
        assert full_msg.content.startswith(event.content)
        assert full_msg.reasoning.startswith(event.reasoning)


class TestToolCallHandler:
    @pytest.fixture
    def tool_registry(self) -> dict[str, FunctionToolSpec]:
        return {
            "web_search": FunctionToolSpec(
                input_cls=WebSearchRequest, func=AsyncMock(return_value="search result")
            ),
            "web_scrape": FunctionToolSpec(
                input_cls=WebScrapeRequest, func=AsyncMock(return_value="scrape result")
            ),
        }

    @pytest.fixture
    def tool_calls(self) -> list[FunctionToolCall]:
        return [
            FunctionToolCall(
                id="search",
                function=FunctionToolCall.Function(
                    name="web_search",
                    arguments='{"query": "example.com"}',
                ),
            ),
            FunctionToolCall(
                id="scrape",
                function=FunctionToolCall.Function(
                    name="web_scrape",
                    arguments='{"url": "example.com"}',
                ),
            ),
        ]

    @pytest.mark.asyncio
    async def test_handle_tool_calls_normal(
        self,
        tool_calls: list[FunctionToolCall],
        tool_registry: dict[str, FunctionToolSpec],
    ):
        tool_msgs = await handle_tool_calls(
            tool_calls=tool_calls, tool_registry=tool_registry
        )
        assert len(tool_msgs) == 2
        assert tool_msgs[0].tool_call_id == "search"
        assert tool_msgs[0].content == "search result"
        assert tool_msgs[1].tool_call_id == "scrape"
        assert tool_msgs[1].content == "scrape result"

    @pytest.mark.asyncio
    async def test_handle_tool_calls_unknown_tool(
        self,
        tool_registry: dict[str, FunctionToolSpec],
    ):
        tool_calls = [
            FunctionToolCall(
                id="",
                function=FunctionToolCall.Function(
                    name="unknown",
                    arguments="{}",
                ),
            )
        ]
        with pytest.raises(LLMToolError, match="not found"):
            await handle_tool_calls(tool_calls=tool_calls, tool_registry=tool_registry)

    @pytest.mark.asyncio
    async def test_handle_tool_calls_invalid_arguments(
        self,
        tool_registry: dict[str, FunctionToolSpec],
    ):
        tool_calls = [
            FunctionToolCall(
                id="",
                function=FunctionToolCall.Function(
                    name="web_search",
                    arguments="",
                ),
            )
        ]
        with pytest.raises(LLMToolError, match="arguments"):
            await handle_tool_calls(tool_calls=tool_calls, tool_registry=tool_registry)

    @pytest.mark.asyncio
    async def test_handle_tool_calls_failure(
        self,
        tool_calls: list[FunctionToolCall],
        tool_registry: dict[str, FunctionToolSpec],
    ):
        failed_tool_idx = random.randrange(len(tool_calls))
        failed_tool_name = tool_calls[failed_tool_idx].function.name
        spec = tool_registry[failed_tool_name]
        spec.func = AsyncMock(side_effect=ToolExecutionError())
        with pytest.raises(ToolExecutionError):
            await handle_tool_calls(tool_calls=tool_calls, tool_registry=tool_registry)


class TestStreamGenerator:
    @pytest.mark.asyncio
    async def test_generate_stream(
        self,
        mock_db: AsyncMock,
        mock_llm: MagicMock,
        mock_is_disconnected: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        conv_id = uuid.uuid7()

        tool_calls = [
            FunctionToolCall(
                id="",
                function=FunctionToolCall.Function(
                    name="web_scrape",
                    arguments='{"url": "example.com"}',
                ),
            )
        ]
        tool_call_streamer = MockLLMStreamer(
            reasoning="Open example.com.",
            tool_calls=tool_calls,
        )

        tool_msg = ToolMessage(
            conversation_id=conv_id, content="# Example Domain", tool_call_id=""
        )
        mock_handle_tool_calls = AsyncMock(return_value=[tool_msg])
        monkeypatch.setattr("api.main.handle_tool_calls", mock_handle_tool_calls)

        content_streamer = MockLLMStreamer(
            reasoning="Show the markdown content as is.",
            content="# Example Domain",
        )

        mock_llm.stream_response.side_effect = [
            tool_call_streamer.stream_response(),
            content_streamer.stream_response(),
        ]

        events = []
        async for data in generate_stream(
            conversation_id=conv_id,
            context=[],
            model="",
            web_access=True,
            llm=mock_llm,
            db=mock_db,
            tool_registry={},
            is_disconnected=mock_is_disconnected,
        ):
            events.append(parse_single_sse_event(data))

        assert events[0]["type"] == "metadata"
        assert events[0]["conversation_id"] == str(conv_id)
        assert events[-1]["type"] == "done"

        assert mock_db.create_message.await_count == 3
        tool_call_msg = tool_call_streamer.chunks[-1]
        content_msg = content_streamer.chunks[-1]
        db_created_msgs = []
        for call in mock_db.create_message.await_args_list:
            db_created_msgs.append(call.kwargs["message"])
        assert db_created_msgs == [tool_call_msg, tool_msg, content_msg]

    @pytest.mark.asyncio
    async def test_generate_stream_llm_streaming_error(
        self,
        mock_llm: MagicMock,
        mock_is_disconnected: AsyncMock,
    ):
        mock_llm.stream_response.side_effect = LLMStreamingError()

        events = []
        async for data in generate_stream(
            conversation_id=uuid.uuid7(),
            context=[],
            model="",
            web_access=True,
            llm=mock_llm,
            db=MagicMock(),
            tool_registry={},
            is_disconnected=mock_is_disconnected,
        ):
            events.append(parse_single_sse_event(data))

        assert len(events) == 1 + 1
        assert events[-1]["type"] == "error"


class TestAppEndpoints:
    @pytest.fixture
    def client(
        self,
        mock_db: AsyncMock,
        mock_llm: MagicMock,
        mock_tool_registry: dict,
        mock_is_disconnected: AsyncMock,
    ) -> Generator[TestClient, None, None]:
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_llm] = lambda: mock_llm
        app.dependency_overrides[get_tool_registry] = lambda: mock_tool_registry
        app.dependency_overrides[get_disconnect_checker] = lambda: mock_is_disconnected
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_create_message_new_conversation(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        conv_id = uuid.uuid7()
        mock_db.create_conversation.return_value = conv_id

        mock_generate_stream = MagicMock(return_value=empty_stream())
        monkeypatch.setattr("api.main.generate_stream", mock_generate_stream)

        payload = {"content": "Hello", "model": "gpt"}
        response = client.post("/messages", json=payload)

        assert response.status_code == 200
        mock_db.create_conversation.assert_awaited_once_with(user_id=0, title="Hello")
        mock_db.load_historical_contents.assert_not_awaited()

        mock_db.create_message.assert_awaited_once()
        user_msg = mock_db.create_message.await_args.kwargs["message"]
        assert isinstance(user_msg, UserMessage)
        assert user_msg.conversation_id == conv_id
        assert user_msg.content == "Hello"

        mock_generate_stream.assert_called_once()
        stream_kwargs = mock_generate_stream.call_args.kwargs
        assert stream_kwargs["conversation_id"] == conv_id
        assert stream_kwargs["context"] == [user_msg]
        assert stream_kwargs["model"] == payload["model"]
        assert stream_kwargs["web_access"] is False

    def test_create_message_existing_conversation(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        conv_id = uuid.uuid7()
        conv_history = [
            UserMessage(conversation_id=conv_id, content="Hello"),
            AssistantMessage(conversation_id=conv_id, content="Hi there!"),
        ]
        mock_db.load_historical_contents.return_value = conv_history.copy()

        mock_generate_stream = MagicMock(return_value=empty_stream())
        monkeypatch.setattr("api.main.generate_stream", mock_generate_stream)

        payload = {
            "conversation_id": str(conv_id),
            "content": "What's going on?",
            "model": "gpt",
            "web_access": True,
        }
        response = client.post("/messages", json=payload)

        assert response.status_code == 200
        mock_db.create_conversation.assert_not_awaited()
        mock_db.load_historical_contents.assert_awaited_once_with(
            conversation_id=conv_id
        )

        mock_db.create_message.assert_awaited_once()
        user_msg = mock_db.create_message.await_args.kwargs["message"]
        assert isinstance(user_msg, UserMessage)
        assert user_msg.conversation_id == conv_id
        assert user_msg.content == "What's going on?"

        mock_generate_stream.assert_called_once()
        stream_kwargs = mock_generate_stream.call_args.kwargs
        assert stream_kwargs["conversation_id"] == conv_id
        assert stream_kwargs["context"] == conv_history + [user_msg]
        assert stream_kwargs["model"] == payload["model"]
        assert stream_kwargs["web_access"] is True

    def test_list_models(self, client: TestClient, mock_llm: MagicMock):
        models = ["claude", "gemini", "gpt"]
        mock_llm.list_models.return_value = models

        response = client.get("/models")

        assert response.status_code == 200
        assert response.json() == models
        mock_llm.list_models.assert_awaited_once()

    def test_list_conversations(self, client: TestClient, mock_db: AsyncMock):
        mock_db.list_conversations.return_value = [
            Conversation(conversation_id=uuid.uuid7(), user_id=0, title="1"),
            Conversation(conversation_id=uuid.uuid7(), user_id=0, title="2"),
            Conversation(conversation_id=uuid.uuid7(), user_id=0, title="3"),
        ]

        response = client.get("/conversations")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        assert [c["title"] for c in body] == ["1", "2", "3"]
        mock_db.list_conversations.assert_awaited_once_with(user_id=0)

    def test_list_messages(self, client: TestClient, mock_db: AsyncMock):
        conv_id = uuid.uuid7()
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
