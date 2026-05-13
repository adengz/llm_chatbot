import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Awaitable, Callable, Protocol

from fastapi import Body, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from api.domain.models import AgentStreamChunk, Conversation, Message, MessageRequest
from api.infra.db import DatabaseException


class LLMClient(Protocol):
    async def list_models(self) -> list[str]: ...

    def stream_response(
        self, context: list[Message], model: str, web_access: bool = False
    ) -> AsyncGenerator[AgentStreamChunk, None]: ...


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
        self, conversation_id: uuid.UUID, cursor: datetime, limit: int = ...
    ) -> list[Message]: ...

    async def load_historical_contents(
        self, conversation_id: uuid.UUID
    ) -> list[Message]: ...


def get_user_id() -> int:
    return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.config import get_settings
    from api.infra.db import DynamoDBClient
    from api.infra.llm import AsyncOpenAIClient
    from api.infra.tools import ddgs_web_search

    settings = get_settings()
    db_client: DBClient = DynamoDBClient(
        endpoint_url=settings.aws_endpoint_url,
        conversations_table=settings.dynamodb_conversations_table,
        messages_table=settings.dynamodb_messages_table,
    )
    llm_client: LLMClient = AsyncOpenAIClient(
        web_search=ddgs_web_search,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    app.state.db_client = db_client
    app.state.llm_client = llm_client
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.exception_handler(DatabaseException)
async def database_exception_handler(request: Request, exc: DatabaseException):
    logger.error(f"Database error: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def get_db(request: Request) -> DBClient:
    return request.app.state.db_client


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_disconnect_checker(request: Request) -> Callable[[], Awaitable[bool]]:
    async def checker() -> bool:
        return await request.is_disconnected()

    return checker


def sse_event(model):
    return f"data: {model.model_dump_json()}\n\n"


@app.get("/health")
async def health():
    return {"status": "ok"}


async def save_instream_message(
    db: DBClient, conversation_id: uuid.UUID, buffer: list[str], tp: str | None
) -> str | None:
    if not buffer or tp not in (
        "reasoning",
        "content",
        "tool_call_req",
        "tool_call_resp",
    ):
        return
    content = "".join(buffer)
    logger.info(f"LLM content of type '{tp}': {content}")
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        type=tp,
        content=content,
    )
    warning = None
    try:
        await db.create_message(message=message)
    except Exception as exc:
        logger.warning(
            f"Failed to save message for conversation {conversation_id}: {exc}"
        )
        warning = sse_event(
            AgentStreamChunk(
                type="warning", exception="Failed to save message: " + str(exc)
            )
        )
    return warning


async def generate_stream(
    conversation_id: uuid.UUID,
    context: list[Message],
    model: str,
    web_access: bool,
    llm: LLMClient,
    db: DBClient,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncGenerator[str, None]:
    yield sse_event(AgentStreamChunk(type="metadata", conversation_id=conversation_id))

    buffer, stream_type = [], None

    async for chunk in llm.stream_response(
        context=context, model=model, web_access=web_access
    ):
        data = None
        match chunk.type:
            case "reasoning" | "content":
                data = chunk.delta
            case "tool_call_req" | "tool_call_resp":
                if chunk.data is not None:
                    data = chunk.data.model_dump_json()
            case _:
                pass

        if chunk.type != stream_type:
            warn = await save_instream_message(
                db=db, conversation_id=conversation_id, buffer=buffer, tp=stream_type
            )
            if warn:
                yield warn
            buffer = []

        if data:
            buffer.append(data)

        stream_type = chunk.type
        yield sse_event(chunk)

        if await is_disconnected():
            logger.info(
                f"Client disconnected during streaming for conversation {conversation_id}"
            )
            await save_instream_message(
                db=db, conversation_id=conversation_id, buffer=buffer, tp=stream_type
            )
            break


@app.get("/models")
async def list_models(llm: LLMClient = Depends(get_llm)) -> list[str]:
    return await llm.list_models()


@app.post("/messages")
async def create_message(
    req: MessageRequest,
    db: DBClient = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
    is_disconnected: Callable[[], Awaitable[bool]] = Depends(get_disconnect_checker),
) -> StreamingResponse:
    user_id = get_user_id()
    message = Message(
        conversation_id=req.conversation_id, role="user", content=req.content
    )

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

    return StreamingResponse(
        generate_stream(
            conversation_id=message.conversation_id,
            context=[message] + context,
            model=req.model,
            web_access=req.web_access,
            llm=llm,
            db=db,
            is_disconnected=is_disconnected,
        ),
        media_type="text/event-stream",
    )


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
