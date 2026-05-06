import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Protocol

import pytest
import pytest_asyncio
from api.domain.models import Message
from api.infra.db import DynamoDBClient, ScyllapyClient
from api.main import DBClient
from scyllapy import Batch, extra_types


class DBHarness(Protocol):
    async def create_tables(self) -> None: ...

    async def drop_tables(self) -> None: ...

    async def truncate_tables(self) -> None: ...

    async def insert_conversation(
        self, user_id: int = 0, title: str = ""
    ) -> uuid.UUID: ...

    async def fetch_conversation_title(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> str | None: ...

    async def count_conversations(self, user_id: int) -> int: ...

    async def count_messages(self, conversation_id: uuid.UUID) -> int: ...

    async def insert_messages(self, messages: list[Message]) -> None: ...

    async def fetch_message_record(
        self, conversation_id: uuid.UUID, created_at: datetime
    ) -> tuple[str, str] | None: ...


@dataclass
class DBTestKit:
    client: DBClient
    harness: DBHarness


class ScyllapyHarness:
    def __init__(self, client: ScyllapyClient):
        self.client = client

    async def create_tables(self) -> None:
        cqls = [
            """
            CREATE TABLE IF NOT EXISTS conversations (
                user_id bigint,
                conversation_id uuid,
                title text,
                PRIMARY KEY (user_id, conversation_id)
            ) WITH CLUSTERING ORDER BY (conversation_id DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS messages (
                conversation_id uuid,
                created_at timestamp,
                role text,
                type text,
                content text,
                PRIMARY KEY (conversation_id, created_at)
            ) WITH CLUSTERING ORDER BY (created_at DESC)
            """,
            "CREATE INDEX IF NOT EXISTS messages_type_idx ON chatbot.messages (type)",
        ]
        for cql in cqls:
            await self.client.scylla.execute(cql)

    async def drop_tables(self) -> None:
        cqls = ["DROP TABLE conversations", "DROP TABLE messages"]
        for cql in cqls:
            await self.client.scylla.execute(cql)

    async def truncate_tables(self) -> None:
        cqls = ["TRUNCATE conversations", "TRUNCATE messages"]
        for cql in cqls:
            await self.client.scylla.execute(cql)

    async def insert_conversation(self, user_id: int = 0, title: str = "") -> uuid.UUID:
        conversation_id = uuid.uuid1()
        await self.client.scylla.execute(
            "INSERT INTO conversations (user_id, conversation_id, title) VALUES (?, ?, ?)",
            [extra_types.BigInt(user_id), conversation_id, title],
        )
        return conversation_id

    async def fetch_conversation_title(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> str | None:
        rows = await self.client.scylla.execute(
            "SELECT title FROM conversations WHERE user_id = ? AND conversation_id = ?",
            [extra_types.BigInt(user_id), conversation_id],
        )
        row = rows.first()
        return row["title"] if row else None

    async def count_conversations(self, user_id: int) -> int:
        rows = await self.client.scylla.execute(
            "SELECT COUNT(1) AS count FROM conversations WHERE user_id = ?",
            [extra_types.BigInt(user_id)],
        )
        row = rows.first()
        return row["count"] if row else 0

    async def count_messages(self, conversation_id: uuid.UUID) -> int:
        rows = await self.client.scylla.execute(
            "SELECT COUNT(1) AS count FROM messages WHERE conversation_id = ?",
            [conversation_id],
        )
        row = rows.first()
        return row["count"] if row else 0

    async def insert_messages(self, messages: list[Message]) -> None:
        batch = Batch()
        for _ in range(len(messages)):
            batch.add_query(
                "INSERT INTO messages (conversation_id, created_at, role, type, content) VALUES (?, ?, ?, ?, ?)",
            )
        await self.client.scylla.batch(
            batch,
            [
                [m.conversation_id, m.created_at, m.role, m.type, m.content]
                for m in messages
            ],
        )

    async def fetch_message_record(
        self, conversation_id: uuid.UUID, created_at: datetime
    ) -> tuple[str, str] | None:
        rows = await self.client.scylla.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? AND created_at = ?",
            [conversation_id, created_at],
        )
        row = rows.first()
        if row is None:
            return None
        return row["role"], row["content"]


class DynamoDBHarness:
    def __init__(self, client: DynamoDBClient) -> None:
        self.client = client

    async def _create_conversations_table(self) -> None:
        async with self.client.get_resource() as resource:
            table = await resource.create_table(
                TableName="conversations",
                KeySchema=[
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "conversation_id", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "user_id", "AttributeType": "N"},
                    {"AttributeName": "conversation_id", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            await table.wait_until_exists()

    async def _create_messages_table(self) -> None:
        async with self.client.get_resource() as resource:
            table = await resource.create_table(
                TableName="messages",
                KeySchema=[
                    {"AttributeName": "conversation_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "conversation_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"},
                    {"AttributeName": "type-created_at", "AttributeType": "S"},
                ],
                LocalSecondaryIndexes=[
                    {
                        "IndexName": "type-created_at-idx",
                        "KeySchema": [
                            {"AttributeName": "conversation_id", "KeyType": "HASH"},
                            {"AttributeName": "type-created_at", "KeyType": "RANGE"},
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },  # TODO: Use KEYS_ONLY and fetch content in application layer to reduce RCU consumption
                    }
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            await table.wait_until_exists()

    async def create_tables(self) -> None:
        await self._create_conversations_table()
        await self._create_messages_table()

    async def drop_tables(self) -> None:
        async with self.client.get_resource() as resource:
            for table_name in ["conversations", "messages"]:
                table = await resource.Table(table_name)
                await table.delete()
                await table.wait_until_not_exists()

    async def truncate_tables(self) -> None:
        await self.drop_tables()
        await self.create_tables()

    async def insert_conversation(self, user_id: int = 0, title: str = "") -> uuid.UUID:
        conversation_id = uuid.uuid7()
        item = {
            "user_id": user_id,
            "conversation_id": str(conversation_id),
            "title": title,
        }
        async with self.client.get_resource() as resource:
            table = await resource.Table("conversations")
            await table.put_item(Item=item)
        return conversation_id

    async def fetch_conversation_title(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> str | None:
        async with self.client.get_resource() as resource:
            table = await resource.Table("conversations")
            response = await table.get_item(
                Key={"user_id": user_id, "conversation_id": str(conversation_id)},
                ProjectionExpression="#title",
                ExpressionAttributeNames={"#title": "title"},
            )
        item = response.get("Item")
        return str(item["title"]) if item else None

    async def count_conversations(self, user_id: int) -> int:
        async with self.client.get_resource() as resource:
            table = await resource.Table("conversations")
            response = await table.query(
                KeyConditionExpression="#user_id = :user_id",
                ExpressionAttributeNames={"#user_id": "user_id"},
                ExpressionAttributeValues={":user_id": user_id},
                Select="COUNT",
            )
        return response.get("Count", 0)

    async def count_messages(self, conversation_id: uuid.UUID) -> int:
        async with self.client.get_resource() as resource:
            table = await resource.Table("messages")
            response = await table.query(
                KeyConditionExpression="#conversation_id = :conversation_id",
                ExpressionAttributeNames={"#conversation_id": "conversation_id"},
                ExpressionAttributeValues={":conversation_id": str(conversation_id)},
                Select="COUNT",
            )
        return response.get("Count", 0)

    async def insert_messages(self, messages: list[Message]) -> None:
        async with self.client.get_resource() as resource:
            table = await resource.Table("messages")
            for message in messages:
                item = {
                    "conversation_id": str(message.conversation_id),
                    "created_at": message.created_at.isoformat(),
                    "role": message.role,
                    "type": message.type,
                    "type-created_at": f"{message.type}#{message.created_at.isoformat()}",
                    "content": message.content,
                }
                await table.put_item(Item=item)

    async def fetch_message_record(
        self, conversation_id: uuid.UUID, created_at: datetime
    ) -> tuple[str, str] | None:
        async with self.client.get_resource() as resource:
            table = await resource.Table("messages")
            response = await table.get_item(
                Key={
                    "conversation_id": str(conversation_id),
                    "created_at": created_at.isoformat(),
                },
                ProjectionExpression="#role, #content",
                ExpressionAttributeNames={"#role": "role", "#content": "content"},
            )
        item = response.get("Item")
        if item is None:
            return None
        return str(item["role"]), str(item["content"])


@pytest_asyncio.fixture(scope="class")
async def scyllapy_testkit() -> AsyncGenerator[DBTestKit, None]:
    client = await ScyllapyClient.create(["localhost:9042"], "chatbot")
    yield DBTestKit(client=client, harness=ScyllapyHarness(client))
    await client.close()


@pytest_asyncio.fixture(scope="class")
async def dynamodb_testkit() -> AsyncGenerator[DBTestKit, None]:
    client = DynamoDBClient(use_local=True)
    yield DBTestKit(client=client, harness=DynamoDBHarness(client))


class DBClientContract:
    @pytest_asyncio.fixture(scope="class")
    async def db_client(self, db_testkit: DBTestKit):
        return db_testkit.client

    @pytest_asyncio.fixture(scope="class")
    async def db_harness(self, db_testkit: DBTestKit) -> DBHarness:
        return db_testkit.harness

    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def setup_and_teardown(self, db_harness: DBHarness):
        await db_harness.create_tables()
        yield
        await db_harness.drop_tables()

    @pytest_asyncio.fixture(autouse=True)
    async def truncate_tables(self, db_harness: DBHarness):
        yield
        await db_harness.truncate_tables()

    @pytest.mark.asyncio
    async def test_create_conversation(
        self, db_client: DBClient, db_harness: DBHarness
    ):
        user_id = 0
        title = "Hello World"
        conversation_id = await db_client.create_conversation(user_id, title)

        stored_title = await db_harness.fetch_conversation_title(
            user_id, conversation_id
        )

        assert stored_title == title

    @pytest.mark.asyncio
    async def test_rename_conversation(
        self, db_client: DBClient, db_harness: DBHarness
    ):
        user_id = 0
        conversation_id = await db_harness.insert_conversation(user_id=user_id)

        new_title = "New Title"
        await db_client.rename_conversation(user_id, conversation_id, new_title)

        stored_title = await db_harness.fetch_conversation_title(
            user_id, conversation_id
        )

        assert stored_title == new_title

    @pytest.mark.asyncio
    async def test_delete_conversation(
        self, db_client: DBClient, db_harness: DBHarness
    ):
        user_id = 0
        conversation_id = await db_harness.insert_conversation(user_id=user_id)

        assert await db_harness.count_conversations(user_id) == 1

        now = datetime.now(timezone.utc)
        messages = [
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=0),
                role="user",
                type="content",
                content="Anyboody?",
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=5),
                role="user",
                type="content",
                content="Hello?",
            ),
        ]
        await db_harness.insert_messages(messages)

        assert await db_harness.count_messages(conversation_id) == 2

        await db_client.delete_conversation(user_id, conversation_id)

        assert await db_harness.count_conversations(user_id) == 0
        assert await db_harness.count_messages(conversation_id) == 0

    @pytest.mark.asyncio
    async def test_list_conversations(self, db_client: DBClient, db_harness: DBHarness):
        user_id = 0
        titles = ["a", "b", "c"]
        for title in titles:
            await db_harness.insert_conversation(user_id=user_id, title=title)
            await asyncio.sleep(0.001)  # Ensure different timestamps for ordering

        res = await db_client.list_conversations(user_id)

        assert len(res) == 3
        assert [r.title for r in res] == titles[::-1]

    @pytest.mark.asyncio
    async def test_create_message(self, db_client: DBClient, db_harness: DBHarness):
        conversation_id = uuid.uuid1()
        role = "user"
        content = "Hello World"
        message = Message(conversation_id=conversation_id, role=role, content=content)
        created_at = message.created_at

        await db_client.create_message(message)
        stored_message = await db_harness.fetch_message_record(
            conversation_id, created_at
        )

        assert stored_message == (role, content)

    @pytest.mark.asyncio
    async def test_list_messages(self, db_client: DBClient, db_harness: DBHarness):
        conversation_id = uuid.uuid1()
        now = datetime.now(timezone.utc)
        messages = [
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=1),
                role="assistant",
                type="content",
                content="2",
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=2),
                role="assistant",
                type="tool_call_resp",
                content="2",
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=3),
                role="assistant",
                type="tool_call_req",
                content="1+1",
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=4),
                role="assistant",
                type="thinking",
                content="Use calculator to calculate 1+1",
            ),
            Message(
                conversation_id=conversation_id,
                created_at=now - timedelta(seconds=5),
                role="user",
                type="content",
                content="1+1=?",
            ),
        ]

        await db_harness.insert_messages(messages)

        assistant_messages = await db_client.list_messages(
            conversation_id, now, limit=4
        )

        assert len(assistant_messages) == 4
        assert [m.content for m in assistant_messages] == [
            "2",
            "2",
            "1+1",
            "Use calculator to calculate 1+1",
        ]
        assert all([m.role == "assistant" for m in assistant_messages])

        user_messages = await db_client.list_messages(
            conversation_id, assistant_messages[-1].created_at, limit=4
        )
        assert len(user_messages) == 1
        assert user_messages[0].content == "1+1=?"
        assert user_messages[0].role == "user"

        content_messages = await db_client.list_messages(
            conversation_id, now, limit=4, content_only=True
        )
        assert len(content_messages) == 2
        assert all([m.type == "content" for m in content_messages])
        assert [m.content for m in content_messages] == ["2", "1+1=?"]
        assert [m.role for m in content_messages] == ["assistant", "user"]


class TestScyllapyClient(DBClientContract):
    @pytest_asyncio.fixture(scope="class")
    async def db_testkit(self, scyllapy_testkit: DBTestKit) -> DBTestKit:
        return scyllapy_testkit


class TestDynamoDBClient(DBClientContract):
    @pytest_asyncio.fixture(scope="class")
    async def db_testkit(self, dynamodb_testkit: DBTestKit) -> DBTestKit:
        return dynamodb_testkit
