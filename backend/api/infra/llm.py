from collections import deque
from typing import AsyncGenerator, Awaitable, Callable, cast

from loguru import logger
from openai import AsyncOpenAI, pydantic_function_tool
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from api.domain.models import AgentStreamChunk, Message
from api.infra.tools import WebSearchRequest, WebSearchResponse


class ToolCallRequest(BaseModel):
    function: str
    request: BaseModel


func_name_2_req_cls: dict[str, type[BaseModel]] = {"web_search": WebSearchRequest}

web_search_tool = pydantic_function_tool(WebSearchRequest, name="web_search")


class AsyncOpenAIClient:
    def __init__(
        self,
        web_search: Callable[[WebSearchRequest], Awaitable[WebSearchResponse]],
        api_key: str,
        base_url: str | None = None,
    ):
        self.web_search = web_search
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def list_models(self) -> list[str]:
        response = await self.client.models.list()
        return sorted([model.id for model in response.data])

    async def stream_response(
        self, context: list[Message], model: str, web_access: bool = False
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        messages = cast(
            list[ChatCompletionMessageParam],
            [m.model_dump(include={"role", "content"}) for m in reversed(context)],
        )
        kwargs = {
            "model": model,
            "messages": messages,
            "stream": True,
            "reasoning_effort": "medium",
        }
        if web_access:
            kwargs["tools"] = [web_search_tool]

        done = False
        tc_queue = deque()

        try:
            while tc_queue or not done:
                while tc_queue:
                    tc = tc_queue.popleft()
                    req = func_name_2_req_cls[tc.function.name].model_validate_json(
                        tc.function.arguments
                    )
                    func = getattr(self, tc.function.name)
                    yield AgentStreamChunk(
                        type="tool_call_req",
                        data=ToolCallRequest(function=tc.function.name, request=req),
                    )
                    resp: BaseModel = await func(req)
                    yield AgentStreamChunk(type="tool_call_resp", data=resp)
                    new_message = {"role": "tool", "tool_call_id": tc.id}
                    new_message["content"] = resp.model_dump_json()
                    kwargs["messages"].append(
                        cast(ChatCompletionMessageParam, new_message)
                    )

                async for chunk in await self.client.chat.completions.create(**kwargs):
                    delta = chunk.choices[0].delta
                    if delta.tool_calls is not None:
                        tc_queue.extend(delta.tool_calls)
                    elif hasattr(delta, "reasoning"):
                        yield AgentStreamChunk(type="reasoning", delta=delta.reasoning)
                    elif delta.content:
                        yield AgentStreamChunk(type="content", delta=delta.content)
                    done = done = chunk.choices[0].finish_reason == "stop"

            yield AgentStreamChunk(type="done")

        except Exception as exc:
            logger.exception("Error in stream_response:")
            yield AgentStreamChunk(
                type="error",
                exception=str(exc),
                status_code=getattr(exc, "status_code", 500),
            )
