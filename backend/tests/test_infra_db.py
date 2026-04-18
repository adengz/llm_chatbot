import uuid
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import pytest
import pytest_asyncio

from scyllapy import extra_types

from api.domain.models import Message, Role
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

    async def insert_message(self, conversation_id: uuid.UUID, created_at: datetime, role: str, content: str) -> None:
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

    async def insert_message(self, conversation_id: uuid.UUID, created_at: datetime, role: str, content: str) -> None:
        await self.client.scylla.execute(
            'INSERT INTO messages (conversation_id, created_at, role, content) VALUES (?, ?, ?, ?)',
            [conversation_id, created_at, role, content],
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
    async def test_create_conversation(self, db_client, db_harness):
        user_id = 0
        title = 'Hello World'
        conversation_id = await db_client.create_conversation(user_id, title)

        stored_title = await db_harness.fetch_conversation_title(user_id, conversation_id)

        assert stored_title == title

    @pytest.mark.asyncio
    async def test_rename_conversation(self, db_client, db_harness):
        user_id = 0
        conversation_id = await db_harness.insert_conversation(user_id=user_id)

        new_title = 'New Title'
        await db_client.rename_conversation(user_id, conversation_id, new_title)

        stored_title = await db_harness.fetch_conversation_title(user_id, conversation_id)

        assert stored_title == new_title

    @pytest.mark.asyncio
    async def test_delete_conversation(self, db_client, db_harness):
        user_id = 0
        conversation_id = await db_harness.insert_conversation(user_id=user_id)

        await db_client.delete_conversation(user_id, conversation_id)

        assert await db_harness.count_conversations(user_id, conversation_id) == 0

    @pytest.mark.asyncio
    async def test_list_conversations(self, db_client, db_harness):
        user_id = 0
        titles = ['a', 'b', 'c']
        for title in titles:
            await db_harness.insert_conversation(user_id=user_id, title=title)
            await asyncio.sleep(0.001)  # Ensure different timestamps for ordering
        
        res = await db_client.list_conversations(user_id)

        assert len(res) == 3
        assert [r.title for r in res] == titles[::-1]

    @pytest.mark.asyncio
    async def test_create_message(self, db_client, db_harness):
        conversation_id = uuid.uuid1()
        role = Role.USER
        content = 'Hello World'
        message = Message(conversation_id=conversation_id, role=role, content=content)
        created_at = message.created_at

        await db_client.create_message(message)
        stored_message = await db_harness.fetch_message_record(conversation_id, created_at)

        assert stored_message == (role.value, content)

    @pytest.mark.asyncio
    async def test_list_messages(self, db_client, db_harness):
        conversation_id = uuid.uuid1()
        now = datetime.now(timezone.utc)
        messages_data = [
            (now - timedelta(minutes=1), Role.ASSISTANT.value, '4'),
            (now - timedelta(minutes=2), Role.USER.value, '2+2=?'),
            (now - timedelta(minutes=3), Role.ASSISTANT.value, '2'),
            (now - timedelta(minutes=4), Role.USER.value, '1+1=?'),
        ]

        for created_at, role, content in messages_data:
            await db_harness.insert_message(conversation_id, created_at, role, content)
        
        limit = 2
        messages1 = await db_client.list_messages(conversation_id, now, limit=limit)

        assert len(messages1) == 2
        assert [m.content for m in messages1] == ['4', '2+2=?']
        assert [m.role for m in messages1] == [Role.ASSISTANT, Role.USER]
        
        messages2 = await db_client.list_messages(conversation_id, messages1[-1].created_at, limit=limit)

        assert len(messages2) == 2
        assert [m.content for m in messages2] == ['2', '1+1=?']
        assert [m.role for m in messages2] == [Role.ASSISTANT, Role.USER]
        
        messages3 = await db_client.list_messages(conversation_id, messages2[-1].created_at, limit=limit)
        
        assert len(messages3) == 0


class TestScyllapyClient(DBClientContract):
    @pytest_asyncio.fixture(scope='class')
    async def db_testkit(self, scyllapy_testkit: DBTestKit) -> DBTestKit:
        return scyllapy_testkit
    