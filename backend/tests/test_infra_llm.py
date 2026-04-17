import os

import pytest
import pytest_asyncio

from api.domain.models import Message, Role
from api.infra.llm import AsyncLLMAssistant


OLLAMA_TEST_MODEL = os.getenv('OLLAMA_TEST_MODEL', 'qwen3:0.6b')


@pytest_asyncio.fixture(scope='session')
async def ollama_assistant() -> AsyncLLMAssistant:
	base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
	return AsyncLLMAssistant(api_key='ollama', base_url=base_url)


class TestAsyncLLMAssistant:

	@pytest.mark.asyncio
	async def test_list_models(self, ollama_assistant: AsyncLLMAssistant):
		models = await ollama_assistant.list_models()

		assert isinstance(models, list)
		assert OLLAMA_TEST_MODEL in models

	@pytest.mark.asyncio
	async def test_stream_response(self, ollama_assistant: AsyncLLMAssistant):
		messages = [
			Message(
				conversation_id=None,
				role=Role.USER,
				content='Reply with exactly one short word.',
			)
		]

		events = []
		async for kind, token in ollama_assistant.stream_response(messages, model=OLLAMA_TEST_MODEL):
			events.append((kind, token))

		assert events
		assert all(kind in {'reasoning', 'content'} for kind, _ in events)
		assert any(kind == 'content' and token.strip() for kind, token in events)
