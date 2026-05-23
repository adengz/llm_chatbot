from typing import AsyncGenerator

from loguru import logger
from openai import AsyncOpenAI
from openai.types.chat.chat_completion_function_tool_param import (
    ChatCompletionFunctionToolParam,
)

from api.domain.models import (
    AgentStreamChunk,
    AssistantMessage,
    FunctionToolCall,
    Message,
)
from api.infra.exceptions import LLMStreamingError, ModelListError, reraise_as

NO_WEB_SYSTEM_PROMPT = "If the user query requires up-to-date information, news, or specific facts from the web, instruct them to enable web access and try again. Do not attempt to answer questions that require web access without it, and do not make up information. If the user query does not require web access, answer the question directly without mentioning web access."
WEB_SYSTEM_PROMPT = "You have access to web search and web scraping tools that allow you to find up-to-date information, news, or specific facts from the web. Use these tools when necessary to answer user queries that require current information."


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
        system_prompt = WEB_SYSTEM_PROMPT if web_access else NO_WEB_SYSTEM_PROMPT
        messages = [{"role": "system", "content": system_prompt}]
        meta_data_fields = {"conversation_id", "created_at"}
        messages.extend([m.model_dump(exclude=meta_data_fields) for m in context])
        logger.info(f"Web access on: {web_access}")
        logger.info(f"Invoking model {model} with context:\n{messages}")

        tools = []
        for tool in self.tools:
            if not web_access and tool["function"]["name"].startswith("web_"):
                continue
            tools.append(tool)

        kwargs = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools

        async with self.client.chat.completions.stream(**kwargs) as stream:
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
