import pytest
import pytest_asyncio
from api.config import get_settings
from api.domain.models import (
    AgentStreamChunk,
    AssistantMessage,
    Message,
    UserMessage,
)
from api.infra.exceptions import LLMStreamingError
from api.infra.llm import AsyncOpenAIClient
from api.infra.tools import WebScrapeRequest
from openai import pydantic_function_tool

OLLAMA_OPENAI_ENDPOINT = "http://localhost:11434/v1"
OLLAMA_TEST_MODEL = get_settings().ollama_test_model

SIMPLE_PROPMT = "Hello"
WEB_SCRAPE_PROMPT = "What content is hosted on this URL: https://example.com?"


@pytest_asyncio.fixture()
async def ollama_client() -> AsyncOpenAIClient:
    tools = [pydantic_function_tool(WebScrapeRequest, name="web_scrape")]
    return AsyncOpenAIClient(
        api_key="sk-", base_url=OLLAMA_OPENAI_ENDPOINT, tools=tools
    )


class TestAsyncOllamaClient:
    @pytest.mark.asyncio
    async def test_list_models(self, ollama_client: AsyncOpenAIClient):
        models = await ollama_client.list_models()

        assert isinstance(models, list)
        assert OLLAMA_TEST_MODEL in models

    async def validate_stream_response(
        self, client: AsyncOpenAIClient, context: list[Message], web_access: bool
    ) -> AssistantMessage:
        buffers = {"reasoning": [], "content": []}
        message = None
        async for chunk in client.stream_response(
            context=context,
            model=OLLAMA_TEST_MODEL,
            web_access=web_access,
        ):
            if isinstance(chunk, AgentStreamChunk):
                buffers[chunk.type].append(chunk.delta)
            else:
                message = chunk

        assert message is not None
        assert "".join(buffers["content"]) == message.content
        if message.reasoning:
            assert "".join(buffers["reasoning"]) == message.reasoning
        else:
            assert len(buffers["reasoning"]) == 0

        return message

    @pytest.mark.asyncio
    async def test_stream_response_simple_prompt(
        self, ollama_client: AsyncOpenAIClient
    ):
        context: list[Message] = [UserMessage(content=SIMPLE_PROPMT)]
        response = await self.validate_stream_response(
            ollama_client, context, web_access=True
        )
        assert response.tool_calls is None

    @pytest.mark.asyncio
    async def test_stream_response_web_access_off(
        self, ollama_client: AsyncOpenAIClient
    ):
        context: list[Message] = [UserMessage(content=WEB_SCRAPE_PROMPT)]
        response = await self.validate_stream_response(
            ollama_client, context, web_access=False
        )
        assert response.tool_calls is None

    @pytest.mark.asyncio
    async def test_stream_response_web_access_on(
        self, ollama_client: AsyncOpenAIClient
    ):
        context: list[Message] = [UserMessage(content=WEB_SCRAPE_PROMPT)]
        response = await self.validate_stream_response(
            ollama_client, context, web_access=True
        )

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].function.name == "web_scrape"

    @pytest.mark.asyncio
    async def test_stream_response_error(self, ollama_client: AsyncOpenAIClient):
        with pytest.raises(LLMStreamingError):
            async for _ in ollama_client.stream_response(
                context=[UserMessage(role="user", content=SIMPLE_PROPMT)],
                model="llama5",
            ):
                pass
