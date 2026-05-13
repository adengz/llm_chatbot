from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from api.config import get_settings
from api.domain.models import Message
from api.infra.llm import AsyncOpenAIClient
from api.infra.tools import WebSearchResponse, WebSearchResult

OLLAMA_OPENAI_ENDPOINT = "http://localhost:11434/v1"
OLLAMA_TEST_MODEL = get_settings().ollama_test_model

SIMPLE_PROPMT = "Reply with exactly one short word."
WEB_ACCESS_PROMPT = "Current price of Bitcoin in USD?"


@pytest_asyncio.fixture()
async def ollama_client() -> AsyncOpenAIClient:
    return AsyncOpenAIClient(
        web_search=AsyncMock(), api_key="sk-", base_url=OLLAMA_OPENAI_ENDPOINT
    )


class TestAsyncOllamaClient:
    @pytest.mark.asyncio
    async def test_list_models(self, ollama_client: AsyncOpenAIClient):
        models = await ollama_client.list_models()

        assert isinstance(models, list)
        assert OLLAMA_TEST_MODEL in models

    @pytest.mark.asyncio
    async def test_stream_response_without_web_access(
        self, ollama_client: AsyncOpenAIClient
    ):
        ollama_client.web_search = AsyncMock()
        chunks = []
        async for chunk in ollama_client.stream_response(
            context=[Message(role="user", content=SIMPLE_PROPMT)],
            model=OLLAMA_TEST_MODEL,
        ):
            chunks.append(chunk)

        assert chunks[-1].type == "done"
        assert chunks[-2].type == "content"
        assert all(chunk.type == "reasoning" for chunk in chunks[:-2])

        assert ollama_client.web_search.await_count == 0

    @pytest.mark.asyncio
    async def test_stream_response_with_web_access(
        self, ollama_client: AsyncOpenAIClient
    ):
        import random

        price = random.uniform(0, 150000)
        mock_response = WebSearchResponse(
            results=[
                WebSearchResult(
                    url="https://www.coindesk.com/price/bitcoin",
                    title="Bitcoin Price",
                    snippet=f"The current price of Bitcoin is ${price:,.2f}.",
                )
            ]
        )
        ollama_client.web_search = AsyncMock(return_value=mock_response)

        chunks = []
        async for chunk in ollama_client.stream_response(
            context=[Message(role="user", content=WEB_ACCESS_PROMPT)],
            model=OLLAMA_TEST_MODEL,
            web_access=True,
        ):
            chunks.append(chunk)

        answer, tool_calls = [], []
        for chunk in chunks:
            if chunk.type == "tool_call_req":
                tool_calls.append(chunk.data)
            elif chunk.type == "content":
                answer.append(chunk.delta)

        assert len(tool_calls) > 0
        assert tool_calls[0].function == "web_search"
        args, _ = ollama_client.web_search.await_args_list[0]
        assert tool_calls[0].request == args[0]

        assert f"{price:,.2f}" in "".join(answer)

    @pytest.mark.asyncio
    async def test_stream_response_model_error(self, ollama_client: AsyncOpenAIClient):
        chunks = []
        async for chunk in ollama_client.stream_response(
            context=[Message(role="user", content=SIMPLE_PROPMT)],
            model="llama5",
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[-1].type == "error"
        assert chunks[-1].status_code == 404

    @pytest.mark.asyncio
    async def test_stream_response_tool_error(self, ollama_client: AsyncOpenAIClient):
        exc = Exception("Too Many Requests")
        setattr(exc, "status_code", 429)
        ollama_client.web_search = AsyncMock(side_effect=exc)

        chunks = []
        async for chunk in ollama_client.stream_response(
            context=[Message(role="user", content=WEB_ACCESS_PROMPT)],
            model=OLLAMA_TEST_MODEL,
            web_access=True,
        ):
            chunks.append(chunk)

        assert len(chunks) > 1
        assert chunks[-1].type == "error"
        assert chunks[-1].status_code == 429
