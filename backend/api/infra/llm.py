from typing import AsyncGenerator, cast

from loguru import logger
from openai import AsyncOpenAI
from openai.types.chat.chat_completion_function_tool_param import (
    ChatCompletionFunctionToolParam,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from api.domain.models import (
    AgentStreamChunk,
    AssistantMessage,
    FunctionToolCall,
    Message,
)
from api.infra.exceptions import LLMStreamingError, ModelListError, reraise_as


class AsyncOpenAIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        tools: list[ChatCompletionFunctionToolParam] | None = None,
    ):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.tools = tools or []

    @reraise_as(ModelListError)
    async def list_models(self) -> list[str]:
        response = await self.client.models.list()
        return sorted([model.id for model in response.data])

    @reraise_as(LLMStreamingError)
    async def stream_response(
        self, context: list[Message], model: str, web_access: bool = False
    ) -> AsyncGenerator[AgentStreamChunk | AssistantMessage, None]:
        meta_data_fields = {"conversation_id", "created_at"}
        messages = [m.model_dump(exclude=meta_data_fields) for m in context]
        logger.info(f"Web access on: {web_access}")
        logger.info(f"Invoking model {model} with context:\n{messages}")

        tools = []
        for tool in self.tools:
            if not web_access and tool["function"]["name"].startswith("web_"):
                continue
            tools.append(tool)

        async with self.client.chat.completions.stream(
            model=model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            tools=tools,
        ) as stream:
            async for event in stream:
                if event.type != "chunk":
                    continue

                delta = event.chunk.choices[0].delta
                if hasattr(delta, "reasoning"):
                    yield AgentStreamChunk(
                        type="reasoning",
                        delta=getattr(delta, "reasoning"),
                    )
                elif delta.content:
                    yield AgentStreamChunk(
                        type="content",
                        delta=delta.content,
                    )

        completion = await stream.get_final_completion()
        message = completion.choices[0].message
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                FunctionToolCall(
                    id=call.id,
                    function=FunctionToolCall.Function(
                        name=call.function.name,
                        arguments=call.function.arguments,
                    ),
                )
                for call in message.tool_calls
            ]
        yield AssistantMessage(
            content=message.content or "",
            reasoning=getattr(message, "reasoning", None),
            tool_calls=tool_calls,
        )
