from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk

from api.domain.models import Message, ReasoningEffort

OLLAMA_LOCAL_URL = 'http://localhost:11434/v1'
OLLAMA_CLOUD_URL = 'https://ollama.com/v1'


class AsyncLLMClient:

    def __init__(self, api_key: str, base_url: str = None):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def list_models(self) -> list[str]:
        response = await self.client.models.list()
        return sorted([model.id for model in response.data]) if response is not None else []

    async def stream_response(
        self,
        context: list[Message],
        model: str, 
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    ) -> AsyncStream[ChatCompletionChunk]:
        messages = [{'role': m.role.value, 'content': m.content} for m in reversed(context)]
        return await self.client.chat.completions.create(
            model=model,
            messages=messages,
            reasoning_effort=reasoning_effort.value,
            stream=True,
        )
    