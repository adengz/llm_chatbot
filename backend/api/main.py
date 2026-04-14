from datetime import datetime, timezone

from fastapi import FastAPI, Request, Depends, HTTPException, Body
from pydantic import UUID1

from api.infra import lifespan
from api.infra.db import AsyncCassandraClient
from api.domain.models import Message, Role, Conversation


def get_user_id() -> int:
    return 0


app = FastAPI(lifespan=lifespan)


def get_db(request: Request) -> AsyncCassandraClient:
    return request.app.state.db_client


@app.post('/messages')
async def create_message(message: Message, db: AsyncCassandraClient = Depends(get_db)):
    if message.role != Role.USER:
        raise HTTPException(status_code=400, detail='Only user messages can be created')

    user_id = get_user_id()
    
    if message.conversation_id is None:
        message.conversation_id = await db.create_conversation(user_id=user_id, title=message.content)
    
    await db.create_message(message=message)

    # TODO: streaming LLM response back to client
    bot_message = Message(conversation_id=message.conversation_id, role=Role.ASSISTANT,
                          content='This is a response from the AI assistant.')
    await db.create_message(message=bot_message)
    return bot_message


@app.get('/conversations')
async def list_conversations(db: AsyncCassandraClient = Depends(get_db)) -> list[Conversation]:
    user_id = get_user_id()
    return await db.list_conversations(user_id=user_id)


@app.get('/conversations/{conversation_id}/messages')
async def list_messages(conversation_id: UUID1, cursor: datetime | None = None, limit: int = 2,
                        db: AsyncCassandraClient = Depends(get_db)) -> list[Message]:
    if cursor is None:
        cursor = datetime.now(timezone.utc)
    return await db.list_messages(conversation_id=conversation_id, cursor=cursor, limit=limit)


@app.delete('/conversations/{conversation_id}')
async def delete_conversation(conversation_id: UUID1, db: AsyncCassandraClient = Depends(get_db)) -> None:
    user_id = get_user_id()
    await db.delete_conversation(user_id=user_id, conversation_id=conversation_id)


@app.patch('/conversations/{conversation_id}')
async def rename_conversation(conversation_id: UUID1, title: str = Body(embed=True),
                              db: AsyncCassandraClient = Depends(get_db)) -> None:
    user_id = get_user_id()
    await db.rename_conversation(user_id=user_id, conversation_id=conversation_id, new_title=title)
