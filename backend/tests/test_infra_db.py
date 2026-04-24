import uuid
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import pytest
import pytest_asyncio

from scyllapy import extra_types, Batch

from api.domain.models import Message
from api.infra.db import ScyllapyClient
from api.main import DBClient


class DBHarness(Protocol):

    async def truncate_tables(self) -> None:
        ...

    async def insert_conversation(self, user_id: int = 0, title: str = '') -> uuid.UUID:
        ...

    async def fetch_conversation_title(self, user_id: int, conversation_id: uuid.UUID) -> str | None:
        ...

    async def count_conversations(self, user_id: int, conversation_id: uuid.UUID) -> int:
        ...

    async def count_messages(self, conversation_id: uuid.UUID) -> int:
        ...

    async def insert_messages(self, messages: list[Message]) -> None:
        ...

    async def fetch_message_record(self, conversation_id: uuid.UUID, created_at: datetime) -> tuple[str, str] | None:
        ...


@dataclass
class DBTestKit:
    client: DBClient
    harness: DBHarness


class ScyllapyHarness:

    def __init__(self, client: ScyllapyClient):
        self.client = client

    async def truncate_tables(self) -> None:
        await self.client.scylla.execute('TRUNCATE conversations')
        await self.client.scylla.execute('TRUNCATE messages')

    async def insert_conversation(self, user_id: int = 0, title: str = '') -> uuid.UUID:
        conversation_id = uuid.uuid1()
        await self.client.scylla.execute(
            'INSERT INTO conversations (user_id, conversation_id, title) VALUES (?, ?, ?)',
            [extra_types.BigInt(user_id), conversation_id, title],
        )
        return conversation_id

    async def fetch_conversation_title(self, user_id: int, conversation_id: uuid.UUID) -> str | None:
        rows = await self.client.scylla.execute(
            'SELECT title FROM conversations WHERE user_id = ? AND conversation_id = ?',
            [extra_types.BigInt(user_id), conversation_id],
        )
        row = rows.first()
        return row['title'] if row else None

    async def count_conversations(self, user_id: int, conversation_id: uuid.UUID) -> int:
        rows = await self.client.scylla.execute(
            'SELECT COUNT(1) AS count FROM conversations WHERE user_id = ? AND conversation_id = ?',
            [extra_types.BigInt(user_id), conversation_id],
        )
        row = rows.first()
        return row['count'] if row else 0
    
    async def count_messages(self, conversation_id: uuid.UUID) -> int:
        rows = await self.client.scylla.execute(
            'SELECT COUNT(1) AS count FROM messages WHERE conversation_id = ?',
            [conversation_id],
        )
        row = rows.first()
        return row['count'] if row else 0

    async def insert_messages(self, messages: list[Message]) -> None:
        batch = Batch()
        for _ in range(len(messages)):
            batch.add_query(
                'INSERT INTO messages (conversation_id, created_at, role, type, content) VALUES (?, ?, ?, ?, ?)',
            )
        await self.client.scylla.batch(
            batch, 
            [[m.conversation_id, m.created_at, m.role, m.type, m.content] for m in messages],
        )

    async def fetch_message_record(self, conversation_id: uuid.UUID, created_at: datetime) -> tuple[str, str] | None:
        rows = await self.client.scylla.execute(
            'SELECT role, content FROM messages WHERE conversation_id = ? AND created_at = ?',
            [conversation_id, created_at],
        )
        row = rows.first()
        if row is None:
            return None
        return row['role'], row['content']


@pytest_asyncio.fixture(scope='session')
async def scyllapy_testkit() -> AsyncIterator[DBTestKit]:
    client = await ScyllapyClient.create(['localhost:9042'], 'chatbot')
    yield DBTestKit(client=client, harness=ScyllapyHarness(client))
    await client.close()


class DBClientContract:

    @pytest_asyncio.fixture(autouse=True)
    async def truncate_tables(self, db_harness: DBHarness):
        yield
        await db_harness.truncate_tables()

    @pytest_asyncio.fixture
    async def db_client(self, db_testkit: DBTestKit):
        return db_testkit.client

    @pytest_asyncio.fixture
    async def db_harness(self, db_testkit: DBTestKit) -> DBHarness:
        return db_testkit.harness

    @pytest.mark.asyncio
    async def test_create_conversation(self, db_client: DBClient, db_harness: DBHarness):
        user_id = 0
        title = 'Hello World'
        conversation_id = await db_client.create_conversation(user_id, title)

        stored_title = await db_harness.fetch_conversation_title(user_id, conversation_id)

        assert stored_title == title

    @pytest.mark.asyncio
    async def test_rename_conversation(self, db_client: DBClient, db_harness: DBHarness):
        user_id = 0
        conversation_id = await db_harness.insert_conversation(user_id=user_id)

        new_title = 'New Title'
        await db_client.rename_conversation(user_id, conversation_id, new_title)

        stored_title = await db_harness.fetch_conversation_title(user_id, conversation_id)

        assert stored_title == new_title

    @pytest.mark.asyncio
    async def test_delete_conversation(self, db_client: DBClient, db_harness: DBHarness):
        user_id = 0
        conversation_id = await db_harness.insert_conversation(user_id=user_id)

        assert await db_harness.count_conversations(user_id, conversation_id) == 1

        now = datetime.now(timezone.utc)
        messages = [
            Message(
                conversation_id=conversation_id, 
                created_at=now - timedelta(seconds=0), 
                role='user', 
                type='content', 
                content='Anyboody?',
            ),
            Message(
                conversation_id=conversation_id, 
                created_at=now - timedelta(seconds=5), 
                role='user', 
                type='content', 
                content='Hello?',
            ),
        ]
        await db_harness.insert_messages(messages)
        
        assert await db_harness.count_messages(conversation_id) == 2

        await db_client.delete_conversation(user_id, conversation_id)

        assert await db_harness.count_conversations(user_id, conversation_id) == 0
        assert await db_harness.count_messages(conversation_id) == 0

    @pytest.mark.asyncio
    async def test_list_conversations(self, db_client: DBClient, db_harness: DBHarness):
        user_id = 0
        titles = ['a', 'b', 'c']
        for title in titles:
            await db_harness.insert_conversation(user_id=user_id, title=title)
            await asyncio.sleep(0.001)  # Ensure different timestamps for ordering
        
        res = await db_client.list_conversations(user_id)

        assert len(res) == 3
        assert [r.title for r in res] == titles[::-1]

    @pytest.mark.asyncio
    async def test_create_message(self, db_client: DBClient, db_harness: DBHarness):
        conversation_id = uuid.uuid1()
        role = 'user'
        content = 'Hello World'
        message = Message(conversation_id=conversation_id, role=role, content=content)
        created_at = message.created_at

        await db_client.create_message(message)
        stored_message = await db_harness.fetch_message_record(conversation_id, created_at)

        assert stored_message == (role, content)

    @pytest.mark.asyncio
    async def test_list_messages(self, db_client: DBClient, db_harness: DBHarness):
        conversation_id = uuid.uuid1()
        now = datetime.now(timezone.utc)
        messages = [
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=1),
                role='assistant',
                type='content',
                content='2',
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=2),
                role='assistant',
                type='tool_call_response',
                content='2',
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=3),
                role='assistant',
                type='tool_call_request',
                content='1+1',
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=4),
                role='assistant',
                type='thinking',
                content='Use calculator to calculate 1+1',
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=5),
                role='user',
                type='content',
                content='1+1=?',
            ),
        ]
        
        await db_harness.insert_messages(messages)
        
        assistant_messages = await db_client.list_messages(conversation_id, now, limit=4)

        assert len(assistant_messages) == 4
        assert [m.content for m in assistant_messages] == ['2', '2', '1+1', 'Use calculator to calculate 1+1']
        assert all([m.role == 'assistant' for m in assistant_messages])

        user_messages = await db_client.list_messages(conversation_id, assistant_messages[-1].created_at, limit=4)
        assert len(user_messages) == 1
        assert user_messages[0].content == '1+1=?'
        assert user_messages[0].role == 'user'

        content_messages = await db_client.list_messages(conversation_id, now, limit=4, content_only=True)
        assert len(content_messages) == 2
        assert all([m.type == 'content' for m in content_messages])
        assert [m.content for m in content_messages] == ['2', '1+1=?']
        assert [m.role for m in content_messages] == ['assistant', 'user']


class TestScyllapyClient(DBClientContract):
    @pytest_asyncio.fixture(scope='class')
    async def db_testkit(self, scyllapy_testkit: DBTestKit) -> DBTestKit:
        return scyllapy_testkit
    