import os

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from api.domain.models import Message
from api.infra.llm import AsyncOllamaClient


OLLAMA_TEST_MODEL = os.getenv('OLLAMA_TEST_MODEL', 'qwen3:0.6b')


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
		PROMPT = 'Reply with exactly one short word.'
		chunks = [chunk async for chunk in ollama_client.stream_response(
			model=OLLAMA_TEST_MODEL,
			messages=[Message(role='user', content=PROMPT)],
		)]
		
		assert chunks[-1].type == 'done'
		assert chunks[-2].type == 'content'
		assert all(chunk.type == 'thinking' for chunk in chunks[:-2])

	@pytest.mark.asyncio
	async def test_stream_response_with_web_access(self, ollama_client: AsyncOllamaClient):
		PROMPT = 'Current price of Bitcoin in USD?'
		
		from pydantic import BaseModel
		class MockWebSearchResponse(BaseModel):
			class MockWebSearchResult(BaseModel):
				content: str
				title: str
			results: list[MockWebSearchResult]

		import random
		price = random.uniform(0, 150000)
		print(price)
		mock_response = MockWebSearchResponse(results=[MockWebSearchResponse.MockWebSearchResult(
			content=f'The current price of Bitcoin is ${price:,.2f} USD.',
			title='Bitcoin Price'
		)])
		ollama_client.client.web_search = AsyncMock(return_value=mock_response)

		chunks = [chunk async for chunk in ollama_client.stream_response(
			model=OLLAMA_TEST_MODEL,
			messages=[Message(role='user', content=PROMPT)],
			web_access=True,
		)]
		
		answer, tool_calls = [], []
		for chunk in chunks:
			if chunk.type == 'tool_call_request':
				tool_calls.append(chunk.data)
			elif chunk.type == 'content':
				answer.append(chunk.delta)
		
		assert len(tool_calls) > 0
		assert tool_calls[0].name == 'web_search'
		assert tool_calls[0].arguments == ollama_client.client.web_search.await_args_list[0].kwargs
		
		assert f'{price:,.2f}' in ''.join(answer)
		