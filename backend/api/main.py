import asyncio
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncGenerator, Awaitable, Callable, Generic, Protocol, TypeVar

from fastapi import Body, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from openai import pydantic_function_tool
from pydantic import BaseModel, ValidationError

from api.domain.models import (
    AgentStreamChunk,
    AssistantMessage,
    Conversation,
    FunctionToolCall,
    Message,
    MessageRequest,
    ToolMessage,
    UserMessage,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class FunctionToolSpec(Generic[T]):
    input_cls: type[T]
    func: Callable[[T], Awaitable[str]]


class LLMClient(Protocol):
    async def list_models(self) -> list[str]: ...

    def stream_response(
        self, context: list[Message], model: str, web_access: bool = False
    ) -> AsyncGenerator[AgentStreamChunk | AssistantMessage, None]: ...


class DBClient(Protocol):
    async def create_conversation(self, user_id: int, title: str) -> uuid.UUID: ...

    async def rename_conversation(
        self, user_id: int, conversation_id: uuid.UUID, new_title: str
    ) -> None: ...

    async def delete_conversation(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> None: ...

    async def list_conversations(self, user_id: int) -> list[Conversation]: ...

    async def create_message(self, message: Message) -> None: ...

    async def scroll_messages(
        self, conversation_id: uuid.UUID, cursor: datetime, limit: int = 100
    ) -> list[Message]: ...

    async def load_historical_contents(
        self, conversation_id: uuid.UUID
    ) -> list[Message]: ...


def get_user_id() -> int:
    return 0


class LLMToolError(Exception):
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.config import get_settings
    from api.infra.db import DynamoDBClient
    from api.infra.llm import AsyncOpenAIClient
    from api.infra.tools import WebSearchRequest, ddgs_web_search

    settings = get_settings()

    tool_registry = {
        "web_search": FunctionToolSpec(
            input_cls=WebSearchRequest, func=ddgs_web_search
        ),
    }
    tools = []
    for name, spec in tool_registry.items():
        tools.append(pydantic_function_tool(spec.input_cls, name=name))

    db_client: DBClient = DynamoDBClient(
        endpoint_url=settings.aws_endpoint_url,
        conversations_table=settings.dynamodb_conversations_table,
        messages_table=settings.dynamodb_messages_table,
    )

    llm_client: LLMClient = AsyncOpenAIClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        tools=tools,
    )

    app.state.tool_registry = tool_registry
    app.state.db_client = db_client
    app.state.llm_client = llm_client
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def get_db(request: Request) -> DBClient:
    return request.app.state.db_client


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_tool_registry(request: Request) -> dict[str, FunctionToolSpec]:
    return request.app.state.tool_registry


def get_disconnect_checker(request: Request) -> Callable[[], Awaitable[bool]]:
    async def checker() -> bool:
        return await request.is_disconnected()

    return checker


async def handle_llm_stream(
    context: list[Message],
    model: str,
    web_access: bool,
    llm: LLMClient,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncGenerator[tuple[AgentStreamChunk | AssistantMessage | None, bool], None]:
    buffer = {"reasoning": [], "content": []}
    async for event in llm.stream_response(
        context=context, model=model, web_access=web_access
    ):
        if await is_disconnected():
            partial_msg = None
            if buffer["reasoning"] or buffer["content"]:
                content = "".join(buffer["content"])
                reasoning = None
                if buffer["reasoning"]:
                    reasoning = "".join(buffer["reasoning"])
                partial_msg = AssistantMessage(
                    content=content,
                    reasoning=reasoning,
                )
            yield partial_msg, True
            return

        if isinstance(event, AgentStreamChunk):
            buffer[event.type].append(event.delta)
        yield event, False


async def handle_tool_calls(
    tool_calls: list[FunctionToolCall], tool_registry: dict[str, FunctionToolSpec]
) -> list[ToolMessage]:
    tasks = []
    for tool_call in tool_calls:
        try:
            spec = tool_registry[tool_call.function.name]
            request = spec.input_cls.model_validate_json(tool_call.function.arguments)
            tasks.append(spec.func(request))
        except KeyError:
            raise LLMToolError(f"Tool not found: {tool_call.function.name}")
        except ValidationError:
            raise LLMToolError(
                f"Invalid arguments for tool {tool_call.function.name}: {tool_call.function.arguments}"
            )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    messages = []
    for tool_call, result in zip(tool_calls, results):
        if isinstance(result, Exception):
            logger.error(f"Tool call error: {result}")
            raise result
        tool_msg = ToolMessage(
            content=str(result),
            tool_call_id=tool_call.id,
        )
        messages.append(tool_msg)
    return messages


SSE_PREFIX = "data: "
SSE_SUFFIX = "\n\n"


def sse_event(model: AgentStreamChunk) -> str:
    return SSE_PREFIX + model.model_dump_json(exclude_none=True) + SSE_SUFFIX


async def generate_stream(
    conversation_id: uuid.UUID,
    context: list[Message],
    model: str,
    web_access: bool,
    llm: LLMClient,
    tool_registry: dict[str, FunctionToolSpec],
    db: DBClient,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncGenerator[str, None]:
    yield sse_event(AgentStreamChunk(type="metadata", conversation_id=conversation_id))

    assistant_msg = None
    disconnected = False
    final_chunk = AgentStreamChunk(type="done")
    try:
        while True:
            async for event, disconnected in handle_llm_stream(
                llm=llm,
                context=context,
                model=model,
                web_access=web_access,
                is_disconnected=is_disconnected,
            ):
                if isinstance(event, AgentStreamChunk):
                    yield sse_event(event)
                    continue
                assistant_msg = event

            if assistant_msg is None:
                break

            assistant_msg.conversation_id = conversation_id
            await db.create_message(message=assistant_msg)

            if not assistant_msg.tool_calls:
                break

            chunk = AgentStreamChunk(
                type="tool_calls",
                data=assistant_msg.tool_calls,
            )
            yield sse_event(chunk)
            context.append(assistant_msg)

            tool_msgs = await handle_tool_calls(
                tool_calls=assistant_msg.tool_calls, tool_registry=tool_registry
            )
            for tool_msg in tool_msgs:
                tool_msg.conversation_id = conversation_id
                await db.create_message(message=tool_msg)
                chunk = AgentStreamChunk(
                    type="tool",
                    tool_call_id=tool_msg.tool_call_id,
                    data=tool_msg.content,
                )
                yield sse_event(chunk)

            context.extend(tool_msgs)
            assistant_msg = None
    except Exception as exc:
        final_chunk = AgentStreamChunk(type="error", exception=str(exc))

    if not disconnected:
        yield sse_event(final_chunk)


@app.post("/messages")
async def create_message(
    req: MessageRequest,
    db: DBClient = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
    tool_registry: dict[str, FunctionToolSpec] = Depends(get_tool_registry),
    is_disconnected: Callable[[], Awaitable[bool]] = Depends(get_disconnect_checker),
) -> StreamingResponse:
    user_id = get_user_id()
    message = UserMessage(conversation_id=req.conversation_id, content=req.content)

    context = []
    if message.conversation_id is None:
        message.conversation_id = await db.create_conversation(
            user_id=user_id, title=message.content
        )
    else:
        context = await db.load_historical_contents(
            conversation_id=message.conversation_id
        )

    await db.create_message(message=message)

    context.append(message)

    return StreamingResponse(
        generate_stream(
            conversation_id=message.conversation_id,
            context=context,
            model=req.model,
            web_access=req.web_access,
            llm=llm,
            tool_registry=tool_registry,
            db=db,
            is_disconnected=is_disconnected,
        ),
        media_type="text/event-stream",
    )


@app.get("/models")
async def list_models(llm: LLMClient = Depends(get_llm)) -> list[str]:
    return await llm.list_models()


@app.get("/conversations")
async def list_conversations(db: DBClient = Depends(get_db)) -> list[Conversation]:
    user_id = get_user_id()
    return await db.list_conversations(user_id=user_id)


@app.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    cursor: datetime | None = None,
    limit: int = 100,
    db: DBClient = Depends(get_db),
) -> list[Message]:
    if cursor is None:
        cursor = datetime.now()
    return await db.scroll_messages(
        conversation_id=conversation_id, cursor=cursor, limit=limit
    )


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID, db: DBClient = Depends(get_db)
) -> None:
    user_id = get_user_id()
    await db.delete_conversation(user_id=user_id, conversation_id=conversation_id)


@app.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: uuid.UUID,
    title: str = Body(embed=True),
    db: DBClient = Depends(get_db),
) -> None:
    user_id = get_user_id()
    await db.rename_conversation(
        user_id=user_id, conversation_id=conversation_id, new_title=title
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
