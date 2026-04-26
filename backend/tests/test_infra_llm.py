import os

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from pydantic import create_model

from api.domain.models import Message
from api.infra.llm import AsyncOllamaClient


OLLAMA_TEST_MODEL = os.getenv('OLLAMA_TEST_MODEL', 'qwen3:0.6b')

SIMPLE_PROPMT = 'Reply with exactly one short word.'
WEB_ACCESS_PROMPT = 'Current price of Bitcoin in USD?'

MockWebSearchResult = create_model('MockWebSearchResult', content=str, title=str)
MockWebSearchResponse = create_model('MockWebSearchResponse', results=(list[MockWebSearchResult], ...))


@pytest_asyncio.fixture()
async def ollama_client() -> AsyncOllamaClient:
	return AsyncOllamaClient()


class TestAsyncOllamaClient:

	@pytest.mark.asyncio
	async def test_list_models(self, ollama_client: AsyncOllamaClient):
		models = await ollama_client.list_models()

		assert isinstance(models, list)
		assert OLLAMA_TEST_MODEL in models

	@pytest.mark.asyncio
	async def test_stream_response_without_web_access(self, ollama_client: AsyncOllamaClient):
		chunks = []
		async for chunk in ollama_client.stream_response(
			context=[Message(role='user', content=SIMPLE_PROPMT)],
			model=OLLAMA_TEST_MODEL,
		):
			chunks.append(chunk)
		
		assert chunks[-1].type == 'done'
		assert chunks[-2].type == 'content'
		assert all(chunk.type == 'thinking' for chunk in chunks[:-2])

	@pytest.mark.asyncio
	async def test_stream_response_with_web_access(self, ollama_client: AsyncOllamaClient):
		import random
		price = random.uniform(0, 150000)
		mock_response = MockWebSearchResponse(results=[MockWebSearchResult(
			content=f'The current price of Bitcoin is ${price:,.2f} USD.',
			title='Bitcoin Price'
		)])
		ollama_client.client.web_search = AsyncMock(return_value=mock_response)

		chunks = []
		async for chunk in ollama_client.stream_response(
			context=[Message(role='user', content=WEB_ACCESS_PROMPT)],
			model=OLLAMA_TEST_MODEL,
			web_access=True,
		):
			chunks.append(chunk)
		
		answer, tool_calls = [], []
		for chunk in chunks:
			if chunk.type == 'tool_call_req':
				tool_calls.append(chunk.data)
			elif chunk.type == 'content':
				answer.append(chunk.delta)
		
		assert len(tool_calls) > 0
		assert tool_calls[0].name == 'web_search'
		assert tool_calls[0].arguments == ollama_client.client.web_search.await_args_list[0].kwargs
		
		assert f'{price:,.2f}' in ''.join(answer)
	
	@pytest.mark.asyncio
	async def test_stream_response_model_error(self, ollama_client: AsyncOllamaClient):
		chunks = []
		async for chunk in ollama_client.stream_response(
			context=[Message(role='user', content=SIMPLE_PROPMT)],
			model='llama5',
		):
			chunks.append(chunk)
		
		assert len(chunks) == 1
		assert chunks[-1].type == 'error'
		assert chunks[-1].status_code == 404

	@pytest.mark.asyncio
	async def test_stream_response_tool_error(self, ollama_client: AsyncOllamaClient):
		ollama_client.client.web_search = AsyncMock(side_effect=Exception('Internal Server Error'))

		chunks = []
		async for chunk in ollama_client.stream_response(
			context=[Message(role='user', content=WEB_ACCESS_PROMPT)],
			model=OLLAMA_TEST_MODEL,
			web_access=True,
		):
			chunks.append(chunk)
		
		assert len(chunks) > 1
		assert chunks[-1].type == 'error'
		assert chunks[-1].status_code == 500
