from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from api.domain.models import Message, ReasoningEffort


class AsyncLLMAssistant:

    def __init__(self, api_key: str, base_url: str = None):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def list_models(self) -> list[str]:
        response = await self.client.models.list()
        return [model.id for model in response.data] if response is not None else []

    async def stream_response(
            self,
            messages: list[Message],
            model: str, 
            reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
        ) -> AsyncGenerator[tuple[str, str]]:
        api_messages = [{'role': message.role.value, 'content': message.content} for message in reversed(messages)]
        stream = await self.client.chat.completions.create(
            model=model,
            messages=api_messages,
            reasoning_effort=reasoning_effort.value,
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices or not chunk.choices[0].delta:
                continue
            
            delta = chunk.choices[0].delta
            if hasattr(delta, 'reasoning'):
                yield 'reasoning', delta.reasoning
            elif delta.content:
                yield 'content', delta.content
