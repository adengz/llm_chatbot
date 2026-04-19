import json
import asyncio
from datetime import datetime, timezone
from typing import Protocol

from pydantic import UUID1
from fastapi import FastAPI, Request, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.infra import lifespan
from api.infra.llm import AsyncLLMAssistant
from api.domain.models import MessageRequest, Message, Role, Conversation


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


def get_llms(request: Request) -> dict[str, AsyncLLMAssistant]:
    return request.app.state.llm_clients


async def list_history(db: DBClient, conversation_id: UUID1, cursor: datetime) -> list[Message]:
    messages = []
    while True:
        batch = await db.list_messages(conversation_id=conversation_id, cursor=cursor, limit=100)
        if not batch:
            break
        messages.extend(batch)
        cursor = batch[-1].created_at
    return messages


@app.get('/models')
async def list_llms(llms: dict[str, AsyncLLMAssistant] = Depends(get_llms)) -> dict[str, list[str]]:
    items = list(llms.items())
    results = await asyncio.gather(*(llm.list_models() for _, llm in items), return_exceptions=True)

    available_models: dict[str, list[str]] = {}
    for (source, _), result in zip(items, results):
        if isinstance(result, Exception):
            continue
        available_models[source] = result

    return available_models


@app.post('/messages')
async def create_message(req: MessageRequest, db: DBClient = Depends(get_db),
                         llms: dict[str, AsyncLLMAssistant] = Depends(get_llms)) -> StreamingResponse:
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

    async def generate():
        conversation_id = str(message.conversation_id)
        yield f"data: {json.dumps({'type': 'metadata', 'conversation_id': conversation_id})}\n\n"

        assistant_content = []
        async for event_type, delta in llm.stream_response(messages=[message] + history, model=req.model, 
                                                           reasoning_effort=req.reasoning_effort):
            if event_type == 'reasoning':
                yield f"data: {json.dumps({'type': 'reasoning', 'delta': delta})}\n\n"
                continue

            assistant_content.append(delta)
            yield f"data: {json.dumps({'type': 'content', 'delta': delta})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        bot_message = Message(conversation_id=message.conversation_id, role=Role.ASSISTANT,
                              content=''.join(assistant_content))
        await db.create_message(message=bot_message)
        
    return StreamingResponse(generate(), media_type='text/event-stream')


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
