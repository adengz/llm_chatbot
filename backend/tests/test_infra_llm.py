import os

import pytest
import pytest_asyncio

from api.domain.models import Message, Role
from api.infra.llm import OLLAMA_LOCAL_URL, AsyncLLMClient


OLLAMA_TEST_MODEL = os.getenv('OLLAMA_TEST_MODEL', 'qwen3:0.6b')


@pytest_asyncio.fixture(scope='session')
async def ollama_assistant() -> AsyncLLMClient:
	return AsyncLLMClient(api_key='ollama', base_url=OLLAMA_LOCAL_URL)


class TestAsyncLLMClient:

	@pytest.mark.asyncio
	async def test_list_models(self, ollama_assistant: AsyncLLMClient):
		models = await ollama_assistant.list_models()

		assert isinstance(models, list)
		assert OLLAMA_TEST_MODEL in models

	@pytest.mark.asyncio
	async def test_stream_response(self, ollama_assistant: AsyncLLMClient):
		messages = [Message(conversation_id=None, role=Role.USER, content='Reply with exactly one short word.')]

		reasoning_chunks, content_chunks = [], []
		stream = await ollama_assistant.stream_response(messages, model=OLLAMA_TEST_MODEL)
		async for chunk in stream:
			if hasattr(chunk.choices[0].delta, 'reasoning'):
				reasoning_chunks.append(chunk.choices[0].delta.reasoning)
			elif chunk.choices[0].delta.content:
				content_chunks.append(chunk)

		assert len(reasoning_chunks) > 0
		assert len(content_chunks) > 0
