import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncGenerator, Protocol

import pytest
import pytest_asyncio
from api.config import get_settings
from api.domain.models import Message
from api.infra.db import DynamoDBClient
from api.main import DBClient


class DBHarness(Protocol):
    async def create_tables(self) -> None: ...

    async def drop_tables(self) -> None: ...

    async def truncate_tables(self) -> None: ...

    async def insert_conversation(
        self, user_id: int = 0, title: str = ""
    ) -> uuid.UUID: ...

    async def fetch_raw_conversation(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> dict | None: ...

    async def count_conversations(self, user_id: int) -> int: ...

    async def count_messages(self, conversation_id: uuid.UUID) -> int: ...

    async def insert_messages(self, messages: list[Message]) -> None: ...

    async def fetch_raw_message(
        self, conversation_id: uuid.UUID, created_at: datetime
    ) -> dict | None: ...


@dataclass
class DBTestKit:
    client: DBClient
    harness: DBHarness


class DynamoDBHarness:
    def __init__(self, client: DynamoDBClient) -> None:
        self.client = client

    async def _create_conversations_table(self) -> None:
        async with self.client.get_resource() as resource:
            table = await resource.create_table(
                TableName=self.client._conversations_table,
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
                TableName=self.client._messages_table,
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
                        "Projection": {"ProjectionType": "KEYS_ONLY"},
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
            for table_name in [
                self.client._conversations_table,
                self.client._messages_table,
            ]:
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
            table = await resource.Table(self.client._conversations_table)
            await table.put_item(Item=item)
        return conversation_id

    async def fetch_raw_conversation(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> dict | None:
        key = {"user_id": user_id, "conversation_id": str(conversation_id)}
        return await self._fetch_raw_item(
            table_name=self.client._conversations_table, key=key
        )

    async def count_conversations(self, user_id: int) -> int:
        async with self.client.get_resource() as resource:
            table = await resource.Table(self.client._conversations_table)
            response = await table.query(
                KeyConditionExpression="#user_id = :user_id",
                ExpressionAttributeNames={"#user_id": "user_id"},
                ExpressionAttributeValues={":user_id": user_id},
                Select="COUNT",
            )
        return response.get("Count", 0)

    async def count_messages(self, conversation_id: uuid.UUID) -> int:
        async with self.client.get_resource() as resource:
            table = await resource.Table(self.client._messages_table)
            response = await table.query(
                KeyConditionExpression="#conversation_id = :conversation_id",
                ExpressionAttributeNames={"#conversation_id": "conversation_id"},
                ExpressionAttributeValues={":conversation_id": str(conversation_id)},
                Select="COUNT",
            )
        return response.get("Count", 0)

    async def insert_messages(self, messages: list[Message]) -> None:
        async with self.client.get_resource() as resource:
            table = await resource.Table(self.client._messages_table)
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

    async def fetch_raw_message(
        self, conversation_id: uuid.UUID, created_at: datetime
    ) -> dict | None:
        key = {
            "conversation_id": str(conversation_id),
            "created_at": created_at.isoformat(),
        }
        return await self._fetch_raw_item(
            table_name=self.client._messages_table, key=key
        )

    async def _fetch_raw_item(self, table_name: str, key: dict) -> dict | None:
        async with self.client.get_resource() as resource:
            table = await resource.Table(table_name)
            response = await table.get_item(Key=key)
        return response.get("Item")


@pytest_asyncio.fixture(scope="class")
async def dynamodb_testkit() -> AsyncGenerator[DBTestKit, None]:
    settings = get_settings()
    client = DynamoDBClient(endpoint_url=settings.aws_endpoint_url)
    yield DBTestKit(client=client, harness=DynamoDBHarness(client))


class DBClientContract:
    @pytest_asyncio.fixture(scope="class")
    async def db_client(self, db_testkit: DBTestKit) -> DBClient:
        return db_testkit.client

    @pytest_asyncio.fixture(scope="class")
    async def db_harness(self, db_testkit: DBTestKit) -> DBHarness:
        return db_testkit.harness

    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def setup_and_teardown(
        self, db_harness: DBHarness
    ) -> AsyncGenerator[None, None]:
        await db_harness.create_tables()
        yield
        await db_harness.drop_tables()

    @pytest_asyncio.fixture(autouse=True)
    async def truncate_tables(
        self, db_harness: DBHarness
    ) -> AsyncGenerator[None, None]:
        yield
        await db_harness.truncate_tables()

    @pytest_asyncio.fixture()
    async def test_conversation_id(
        self, db_harness: DBHarness
    ) -> AsyncGenerator[uuid.UUID, None]:
        user_id = 0
        conversation_id = await db_harness.insert_conversation(
            user_id, "Test Conversation"
        )
        now = datetime.now()
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
                type="reasoning",
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

        assert await db_harness.count_conversations(user_id) == 1
        assert await db_harness.count_messages(conversation_id) == 5
        yield conversation_id

    @pytest.mark.asyncio
    async def test_create_conversation(
        self,
        db_client: DBClient,
        db_harness: DBHarness,
        conversation_idx_fields: list[str],
    ):
        user_id = 0
        conversation_id = await db_client.create_conversation(user_id, "Hello World")

        conversation = await db_harness.fetch_raw_conversation(user_id, conversation_id)
        assert conversation is not None
        assert conversation["user_id"] == user_id
        assert conversation["conversation_id"] == str(conversation_id)
        assert conversation["title"] == "Hello World"
        for field in conversation_idx_fields:
            assert field in conversation

    @pytest.mark.asyncio
    async def test_rename_conversation(
        self, db_client: DBClient, db_harness: DBHarness
    ):
        user_id = 0
        conversation_id = await db_harness.insert_conversation(user_id, "Old Title")

        conversation = await db_harness.fetch_raw_conversation(user_id, conversation_id)
        assert conversation is not None
        assert conversation["title"] == "Old Title"

        await db_client.rename_conversation(user_id, conversation_id, "New Title")

        updated_conversation = await db_harness.fetch_raw_conversation(
            user_id, conversation_id
        )
        assert updated_conversation is not None
        assert updated_conversation["conversation_id"] == str(conversation_id)
        assert updated_conversation["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_delete_conversation(
        self,
        db_client: DBClient,
        db_harness: DBHarness,
        test_conversation_id: uuid.UUID,
    ):
        user_id = 0
        await db_client.delete_conversation(user_id, test_conversation_id)

        assert await db_harness.count_conversations(user_id) == 0
        assert await db_harness.count_messages(test_conversation_id) == 0

    @pytest.mark.asyncio
    async def test_list_conversations(self, db_client: DBClient, db_harness: DBHarness):
        user_id = 0
        titles = ["a", "b", "c"]
        for title in titles:
            await db_harness.insert_conversation(user_id, title)
            await asyncio.sleep(0.001)  # Ensure different timestamps for ordering

        res = await db_client.list_conversations(user_id)

        assert len(res) == 3
        assert [r.title for r in res] == titles[::-1]

    @pytest.mark.asyncio
    async def test_create_message(
        self, db_client: DBClient, db_harness: DBHarness, message_idx_fields: list[str]
    ):
        conversation_id = uuid.uuid1()
        role = "user"
        content = "Hello World"
        message = Message(conversation_id=conversation_id, role=role, content=content)
        created_at = message.created_at

        await db_client.create_message(message)
        stored_message = await db_harness.fetch_raw_message(conversation_id, created_at)

        assert stored_message is not None
        assert stored_message["role"] == role
        assert stored_message["content"] == content
        for field in message_idx_fields:
            assert field in stored_message

    @pytest.mark.asyncio
    async def test_scroll_messages(
        self, db_client: DBClient, test_conversation_id: uuid.UUID
    ):
        now = datetime.now()
        latest_messages = await db_client.scroll_messages(
            test_conversation_id, now, limit=4
        )
        assert len(latest_messages) == 4
        assert [m.content for m in latest_messages] == [
            "2",
            "2",
            "1+1",
            "Use calculator to calculate 1+1",
        ]
        assert all([m.role == "assistant" for m in latest_messages])

        second_latest_messages = await db_client.scroll_messages(
            test_conversation_id, latest_messages[-1].created_at, limit=4
        )
        assert len(second_latest_messages) == 1
        assert second_latest_messages[0].content == "1+1=?"
        assert second_latest_messages[0].role == "user"

        no_more_messages = await db_client.scroll_messages(
            test_conversation_id, second_latest_messages[-1].created_at, limit=4
        )
        assert len(no_more_messages) == 0

    @pytest.mark.asyncio
    async def test_load_historical_contents(
        self, db_client: DBClient, test_conversation_id: uuid.UUID
    ):
        messages = await db_client.load_historical_contents(test_conversation_id)
        assert len(messages) == 2
        assert [m.content for m in messages] == ["2", "1+1=?"]
        assert [m.role for m in messages] == ["assistant", "user"]
        assert all([m.type == "content" for m in messages])


class TestDynamoDBClient(DBClientContract):
    @pytest_asyncio.fixture()
    async def conversation_idx_fields(self) -> list[str]:
        fields = ["user_id", "conversation_id"]
        assert len(fields) > 0
        return fields

    @pytest_asyncio.fixture()
    async def message_idx_fields(self) -> list[str]:
        fields = ["conversation_id", "created_at", "type-created_at"]
        assert len(fields) > 0
        return fields

    @pytest_asyncio.fixture(scope="class")
    async def db_testkit(self, dynamodb_testkit: DBTestKit) -> DBTestKit:
        return dynamodb_testkit
