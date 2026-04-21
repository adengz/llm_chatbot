import json
import asyncio
from datetime import datetime, timezone
from typing import Protocol, Callable, Awaitable, AsyncGenerator

from pydantic import UUID1
from fastapi import FastAPI, Request, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.infra import lifespan
from api.infra.llm import AsyncLLMClient
from api.domain.models import MessageRequest, ReasoningEffort, Message, Role, Conversation


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

    async def list_messages(self, conversation_id: UUID1, cursor: datetime, limit: int = 2) -> list[Message]:
        ...


def get_user_id() -> int:
    return 0


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


def get_db(request: Request) -> DBClient:
    return request.app.state.db_client


def get_llms(request: Request) -> dict[str, AsyncLLMClient]:
    return request.app.state.llm_clients


def get_disconnect_checker(request: Request) -> Callable[[], Awaitable[bool]]:
    async def checker() -> bool:
        return await request.is_disconnected()
    return checker


async def list_history(db: DBClient, conversation_id: UUID1, cursor: datetime) -> list[Message]:
    messages = []
    while True:
        batch = await db.list_messages(conversation_id=conversation_id, cursor=cursor, limit=100)
        if not batch:
            break
        messages.extend(batch)
        cursor = batch[-1].created_at
    return messages


sse_event = lambda obj: f'data: {json.dumps(obj)}\n\n'


async def generate_stream(
    conversation_id: UUID1,
    context: list[Message],
    llm: AsyncLLMClient,
    model: str,
    reasoning_effort: ReasoningEffort,
    db: DBClient,
    is_disconnected: Callable[[], Awaitable[bool]]
):
    yield sse_event({'type': 'metadata', 'conversation_id': str(conversation_id)})

    assistant_content = []
    stream = None
    client_disconnected = False

    try:
        stream = await llm.stream_response(context=context, model=model, reasoning_effort=reasoning_effort)
        async for chunk in stream:
            client_disconnected = await is_disconnected()
            if client_disconnected:
                assistant_content = None
                break

            if hasattr(chunk.choices[0].delta, 'reasoning'):
                yield sse_event({'type': 'reasoning', 'delta': chunk.choices[0].delta.reasoning})
            elif chunk.choices[0].delta.content:
                assistant_content.append(chunk.choices[0].delta.content)
                yield sse_event({'type': 'content', 'delta': chunk.choices[0].delta.content})

        if not client_disconnected:
            yield sse_event({'type': 'done'})

    except Exception as exc:
        assistant_content = None
        if not client_disconnected:
            yield sse_event({'type': 'error', 'exception': str(exc)})
    finally:
        if stream is not None:
            await stream.close()

    if assistant_content:
        message = Message(conversation_id=conversation_id, role=Role.ASSISTANT, content=''.join(assistant_content))
        await db.create_message(message=message)


@app.get('/models')
async def list_llms(llms: dict[str, AsyncLLMClient] = Depends(get_llms)) -> dict[str, list[str]]:
    items = list(llms.items())
    results = await asyncio.gather(*(llm.list_models() for _, llm in items), return_exceptions=True)

    available_models: dict[str, list[str]] = {}
    for (source, _), result in zip(items, results):
        if isinstance(result, Exception):
            continue
        available_models[source] = result

    return available_models


@app.post('/messages')
async def create_message(
    req: MessageRequest,
    db: DBClient = Depends(get_db), 
    llms: dict[str, AsyncLLMClient] = Depends(get_llms),
    is_disconnected: Callable[[], Awaitable[bool]] = Depends(get_disconnect_checker),
) -> StreamingResponse:
    llm = llms.get(req.model_source)
    if llm is None:
        raise HTTPException(status_code=400, detail=f'Unsupported model source: {req.model_source}')
    
    user_id = get_user_id()
    message = Message(conversation_id=req.conversation_id, role=Role.USER, content=req.content)
    
    history = []
    if req.conversation_id is None:
        message.conversation_id = await db.create_conversation(user_id=user_id, title=message.content)
    else:
        history = await list_history(db=db, conversation_id=message.conversation_id, cursor=message.created_at)
    
    await db.create_message(message=message)
        
    return StreamingResponse(
        generate_stream(
            conversation_id=message.conversation_id, 
            context=[message] + history, 
            llm=llm, 
            model=req.model,
            reasoning_effort=req.reasoning_effort, 
            db=db, 
            is_disconnected=is_disconnected
        ), 
        media_type='text/event-stream'
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
