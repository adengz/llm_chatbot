from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Protocol, Callable, Awaitable, Literal, AsyncGenerator

from pydantic import UUID1
from fastapi import FastAPI, Request, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from api.domain.models import AgentStreamChunk, MessageRequest, Message, Conversation
from api.infra.exceptions import DatabaseException


class LLMClient(Protocol):

    async def list_models(self) -> list[str]:
        ...

    async def stream_response(self, context: list[Message], model: str, web_access: bool = False) \
        -> AsyncGenerator[AgentStreamChunk, None]:
        ...


class DBClient(Protocol):

    async def create_conversation(self, user_id: int, title: str) -> UUID1:
        ...

    async def rename_conversation(self, user_id: int, conversation_id: UUID1, new_title: str) -> None:
        ...

    async def delete_conversation(self, user_id: int, conversation_id: UUID1) -> None:
        ...

    async def list_conversations(self, user_id: int) -> list[Conversation]:
        ...

    async def create_message(self, message: Message) -> None:
        ...

    async def list_messages(self, conversation_id: UUID1, cursor: datetime, limit: int = 2, 
                            content_only: bool = False) -> list[Message]:
        ...


def get_user_id() -> int:
    return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.infra.db import ScyllapyClient
    db_client = await ScyllapyClient.create(['localhost:9042'], 'chatbot')
    app.state.db_client = db_client
    from api.infra.llm import AsyncOllamaClient
    app.state.llm_client = AsyncOllamaClient(use_cloud=True)
    yield
    await db_client.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


@app.exception_handler(DatabaseException)
async def database_exception_handler(request: Request, exc: DatabaseException):
    return JSONResponse(status_code=500, content={'detail': str(exc)})


def get_db(request: Request) -> DBClient:
    return request.app.state.db_client


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_disconnect_checker(request: Request) -> Callable[[], Awaitable[bool]]:
    async def checker() -> bool:
        return await request.is_disconnected()
    return checker


async def list_context(db: DBClient, conversation_id: UUID1, cursor: datetime) -> list[Message]:
    messages = []
    while True:
        batch = await db.list_messages(conversation_id=conversation_id, cursor=cursor, limit=100, content_only=True)
        if not batch:
            break
        messages.extend(batch)
        cursor = batch[-1].created_at
    return messages


sse_event = lambda model: f'data: {model.model_dump_json()}\n\n'


async def save_instream_message(db: DBClient, conversation_id: UUID1, buffer: list[str], 
                                tp: Literal['tool_call_req', 'tool_call_resp', 'thinking', 'content']) -> str | None:
    if not buffer:
        return 
    message = Message(conversation_id=conversation_id, role='assistant', type=tp, content=''.join(buffer))
    warning = None
    try:
        await db.create_message(message=message)
        return
    except Exception as exc:
        warning = sse_event(AgentStreamChunk(type='warning', exception='Failed to save message: ' + str(exc)))
    return warning


async def generate_stream(conversation_id: UUID1, context: list[Message], model: str, web_access: bool,
                          llm: LLMClient, db: DBClient, is_disconnected: Callable[[], Awaitable[bool]]) \
                              -> AsyncGenerator[str, None]:
    yield sse_event(AgentStreamChunk(type='metadata', conversation_id=conversation_id))

    buffer, stream_type = [], None

    async for chunk in llm.stream_response(context=context, model=model, web_access=web_access):
        data = None
        match chunk.type:
            case 'thinking' | 'content':
                data = chunk.delta
            case 'tool_call_req' | 'tool_call_resp':
                data = chunk.data.model_dump_json()
            case _:
                pass

        if chunk.type != stream_type:
            warning = await save_instream_message(db=db, conversation_id=conversation_id, buffer=buffer, tp=stream_type)
            if warning:
                yield warning
            buffer = []

        if data:
            buffer.append(data)
        
        stream_type = chunk.type
        yield sse_event(chunk)

        if await is_disconnected():
            await save_instream_message(db=db, conversation_id=conversation_id, buffer=buffer, tp=stream_type)
            break


@app.get('/models')
async def list_models(llm: LLMClient = Depends(get_llm)) -> list[str]:
    return await llm.list_models()


@app.post('/messages')
async def create_message(req: MessageRequest, db: DBClient = Depends(get_db),
                         llm: LLMClient = Depends(get_llm), 
                         is_disconnected: Callable[[], Awaitable[bool]] = Depends(get_disconnect_checker)) \
                            -> StreamingResponse:
    user_id = get_user_id()
    message = Message(conversation_id=req.conversation_id, role='user', content=req.content)
    
    context = []
    if req.conversation_id is None:
        message.conversation_id = await db.create_conversation(user_id=user_id, title=message.content)
    else:
        context = await list_context(db=db, conversation_id=message.conversation_id, cursor=message.created_at)
    
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
        media_type='text/event-stream',
    )


@app.get('/conversations')
async def list_conversations(db: DBClient = Depends(get_db)) -> list[Conversation]:
    user_id = get_user_id()
    return await db.list_conversations(user_id=user_id)


@app.get('/conversations/{conversation_id}/messages')
async def list_messages(conversation_id: UUID1, cursor: datetime | None = None, limit: int = 2,
                        db: DBClient = Depends(get_db)) -> list[Message]:
    if cursor is None:
        cursor = datetime.now(timezone.utc)
    return await db.list_messages(conversation_id=conversation_id, cursor=cursor, limit=limit)


@app.delete('/conversations/{conversation_id}')
async def delete_conversation(conversation_id: UUID1, db: DBClient = Depends(get_db)) -> None:
    user_id = get_user_id()
    await db.delete_conversation(user_id=user_id, conversation_id=conversation_id)


@app.patch('/conversations/{conversation_id}')
async def rename_conversation(conversation_id: UUID1, title: str = Body(embed=True),
                              db: DBClient = Depends(get_db)) -> None:
    user_id = get_user_id()
    await db.rename_conversation(user_id=user_id, conversation_id=conversation_id, new_title=title)
