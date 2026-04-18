import uuid
import datetime
from typing import Self, Any

from pydantic import UUID1
from scyllapy import Scylla, PreparedQuery, QueryResult, extra_types

from api.domain.models import Conversation, Message, Role


class ScyllapyClient:

    def __init__(self, scylla: Scylla):
        self.scylla = scylla
        self._prepared_statements = {}

    @classmethod
    async def create(cls, contact_points: list[str], keyspace: str | None = None) -> Self:
        scylla = Scylla(contact_points, keyspace=keyspace)
        await scylla.startup()
        return cls(scylla)

    async def close(self) -> None:
        await self.scylla.shutdown()

    async def _prepare(self, query: str) -> PreparedQuery:
        prepared = self._prepared_statements.get(query)
        if prepared is None:
            prepared = await self.scylla.prepare(query)
            self._prepared_statements[query] = prepared
        return prepared

    async def _execute_prepared(self, query: str, parameters: list[Any]) -> QueryResult:
        prepared = await self._prepare(query)
        return await self.scylla.execute(prepared, parameters)

    async def create_conversation(self, user_id: int, title: str) -> UUID1:
        conversation_id = uuid.uuid1()
        await self._execute_prepared(
            'INSERT INTO conversations (user_id, conversation_id, title) VALUES (?, ?, ?)',
            [extra_types.BigInt(user_id), conversation_id, title],
        )
        return conversation_id

    async def rename_conversation(self, user_id: int, conversation_id: UUID1, new_title: str) -> None:
        await self._execute_prepared(
            'UPDATE conversations SET title = ? WHERE user_id = ? AND conversation_id = ?',
            [new_title, extra_types.BigInt(user_id), conversation_id],
        )

    async def delete_conversation(self, user_id: int, conversation_id: UUID1) -> None:
        await self._execute_prepared(
            'DELETE FROM conversations WHERE user_id = ? AND conversation_id = ?',
            [extra_types.BigInt(user_id), conversation_id],
        )

    async def list_conversations(self, user_id: int) -> list[Conversation]:
        result = await self._execute_prepared(
            'SELECT conversation_id, title FROM conversations WHERE user_id = ?',
            [extra_types.BigInt(user_id)],
        )
        return [
            Conversation(
                user_id=user_id,
                conversation_id=row['conversation_id'],
                title=row['title'],
            )
            for row in result.all()
        ]

    async def create_message(self, message: Message) -> None:
        await self._execute_prepared(
            'INSERT INTO messages (conversation_id, created_at, role, content) VALUES (?, ?, ?, ?)',
            [message.conversation_id, message.created_at, message.role.value, message.content],
        )

    async def list_messages(self, conversation_id: UUID1, cursor: datetime.datetime, limit: int = 2) -> list[Message]:
        result = await self._execute_prepared(
            'SELECT created_at, role, content FROM messages WHERE conversation_id = ? AND created_at < ? LIMIT ?',
            [conversation_id, cursor, limit],
        )
        return [
            Message(
                conversation_id=conversation_id,
                created_at=row['created_at'],
                role=Role(row['role']),
                content=row['content'],
            )
            for row in result.all()
        ]
        