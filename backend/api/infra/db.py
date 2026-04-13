import uuid
import datetime
from typing import Self

from pydantic import UUID1
from async_cassandra import AsyncCassandraSession, AsyncCluster

from api.domain.models import Conversation, Message, Role


class AsyncCassandraClient:

    def __init__(self, session: AsyncCassandraSession):
        self.session = session

    @classmethod
    async def create(cls, contact_points: list[str], keyspace: str) -> Self:
        cluster = AsyncCluster(contact_points)
        session = await cluster.connect(keyspace)
        return cls(session)

    async def create_conversation(self, user_id: int, title: str) -> UUID1:
        conversation_id = uuid.uuid1()
        query = await self.session.prepare('INSERT INTO conversations (user_id, conversation_id, title) '\
                                           'VALUES (?, ?, ?)')
        await self.session.execute(query, (user_id, conversation_id, title))
        return conversation_id
    
    async def rename_conversation(self, user_id: int, conversation_id: UUID1, new_title: str) -> None:
        query = await self.session.prepare('UPDATE conversations SET title = ? '\
                                           'WHERE user_id = ? AND conversation_id = ?')
        await self.session.execute(query, (new_title, user_id, conversation_id))
    
    async def delete_conversation(self, user_id: int, conversation_id: UUID1) -> None:
        query = await self.session.prepare('DELETE FROM conversations WHERE user_id = ? AND conversation_id = ?')
        await self.session.execute(query, (user_id, conversation_id))

    async def list_conversations(self, user_id: int) -> list[Conversation]:
        query = await self.session.prepare('SELECT conversation_id, title FROM conversations WHERE user_id = ?')
        rows = await self.session.execute(query, (user_id,))
        return [Conversation(user_id=user_id, conversation_id=row.conversation_id, title=row.title) for row in rows]
    
    async def create_message(self, message: Message) -> datetime.datetime:
        created_at = datetime.datetime.now(datetime.timezone.utc)
        query = await self.session.prepare('INSERT INTO messages (conversation_id, created_at, role, content) '\
                                           'VALUES (?, ?, ?, ?)')
        await self.session.execute(query, (message.conversation_id, created_at, message.role.value, message.content))
        return created_at
    
    async def list_messages(self, conversation_id: UUID1, cursor: datetime.datetime, limit: int = 2) -> list[Message]:
        query = await self.session.prepare('SELECT created_at, role, content FROM messages '
                                           'WHERE conversation_id = ? AND created_at <= ? LIMIT ?')
        rows = await self.session.execute(query, (conversation_id, cursor, limit))
        return [
            Message(
                conversation_id=conversation_id,
                created_at=row.created_at,
                role=Role(row.role),
                content=row.content,
            )
            for row in rows
        ]
        