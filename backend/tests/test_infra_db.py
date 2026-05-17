import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncGenerator, Protocol

import pytest
import pytest_asyncio
from api.config import get_settings
from api.domain.models import (
    AssistantMessage,
    FunctionToolCall,
    Message,
    ToolMessage,
    UserMessage,
)
from api.infra.db import DynamoDBClient, tool_calls_adapter
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
        items = []
        for message in messages:
            item = {
                "conversation_id": str(message.conversation_id),
                "created_at": message.created_at.isoformat(),
                "role": message.role,
                "content": message.content,
            }
            if isinstance(message, AssistantMessage):
                if message.reasoning:
                    item["reasoning"] = message.reasoning
                if message.tool_calls is not None:
                    tool_calls_bytes = tool_calls_adapter.dump_json(message.tool_calls)
                    item["tool_calls"] = tool_calls_bytes.decode()
            elif isinstance(message, ToolMessage):
                item["tool_call_id"] = message.tool_call_id
            items.append(item)

        async with self.client.get_resource() as resource:
            table = await resource.Table(self.client._messages_table)
            async with table.batch_writer() as batch:
                for item in items:
                    await batch.put_item(Item=item)

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
    async def client(self, testkit: DBTestKit) -> DBClient:
        return testkit.client

    @pytest_asyncio.fixture(scope="class")
    async def harness(self, testkit: DBTestKit) -> DBHarness:
        return testkit.harness

    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def setup_and_teardown(
        self, harness: DBHarness
    ) -> AsyncGenerator[None, None]:
        await harness.create_tables()
        yield
        await harness.drop_tables()

    @pytest_asyncio.fixture(autouse=True)
    async def truncate_tables(self, harness: DBHarness) -> AsyncGenerator[None, None]:
        yield
        await harness.truncate_tables()

    @pytest_asyncio.fixture()
    async def test_conv_id(self, harness: DBHarness) -> AsyncGenerator[uuid.UUID, None]:
        user_id = 0
        conv_id = await harness.insert_conversation(user_id, "Test Conversation")
        message_data = [
            {
                "role": "user",
                "content": "example.com, what is special about this domain?",
            },
            {
                "role": "assistant",
                "reasoning": "We need info. Search.",
                "tool_calls": [
                    FunctionToolCall(
                        id="call-0",
                        function=FunctionToolCall.Function(
                            name="web_search", arguments='{"query": "example.com"}'
                        ),
                    )
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-0",
                "content": '[{"title": "Example.com", "url": "https://en.wikipedia.org/wiki/Example.com", "snippet": "The domain names example.com, example.net, example.org, and example.edu are second-level domain names in the Domain Name System of the Internet. They are reserved by the Internet Assigned Numbers Authority (IANA) at the direction of the Internet (IETF) as special-use domain names for documentation purposes. The domain names are used widely in books, tutorials, sample network configurations, and generally as examples for the use of domain names. The Internet Corporation for Assigned Names and Numbers (ICANN) operates websites for these domains with content that reflects their purpose."}]',
            },
            {
                "role": "assistant",
                "reasoning": "Answer.",
                "content": "example.com (and its siblings example.net, example.org, example.edu) is not simply a regular web‑domain. It is a special‑use domain that the Internet Assigned Numbers Authority (IANA) set aside for documentation and sample usage.",
            },
            {
                "role": "user",
                "content": "How many sibling domains are there including example.com?",
            },
            {
                "role": "assistant",
                "reasoning": "Count siblings. Putting them in a JSON array and counting the length.",
                "tool_calls": [
                    FunctionToolCall(
                        id="call-1",
                        function=FunctionToolCall.Function(
                            name="json_array_length",
                            arguments='["example.com", "example.net", "example.org", "example.edu"]',
                        ),
                    )
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": "4",
            },
            {
                "role": "assistant",
                "reasoning": "Answer.",
                "content": "There are 4 sibling domains: example.com, example.net, example.org, and example.edu.",
            },
            {
                "role": "user",
                "content": "Show me some key facts about example.com",
            },
            {
                "role": "assistant",
                "reasoning": "Find key facts from wikipedia's infobox.",
                "tool_calls": [
                    FunctionToolCall(
                        id="call-2",
                        function=FunctionToolCall.Function(
                            name="wikipedia_scrape",
                            arguments='{"wiki": "Example.com", "element": "infobox"}',
                        ),
                    )
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-2",
                "content": '{"Type of site": "Reserved domain", "Available in": "English", "Owner": "Internet Assigned Numbers Authority[[1]](https://en.wikipedia.org/wiki/Example.com#cite_note-1)", "URL": "[www.example.com](https://www.example.com)", "Launched": "1 January 1999", "Current status": "Online"}',
            },
            {
                "role": "assistant",
                "reasoning": "Answer in markdown.",
                "content": "- **Type of site**: Reserved domain\n- **Available in**: English\n- **Owner**: Internet Assigned Numbers Authority[[1]](https://en.wikipedia.org/wiki/Example.com#cite_note-1)\n- **URL**: [www.example.com](https://www.example.com)\n- **Launched**: 1 January 1999\n- **Current status**: Online",
            },
            {
                "role": "user",
                "content": "What is the content hosted on example.com?",
            },
            {
                "role": "assistant",
                "reasoning": "Open example.com.",
                "tool_calls": [
                    FunctionToolCall(
                        id="call-3",
                        function=FunctionToolCall.Function(
                            name="web_scrape", arguments='{"url": "example.com"}'
                        ),
                    )
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-3",
                "content": "# Example Domain\n\nThis domain is for use in documentation examples without needing permission. Avoid use in operations.\n\n[Learn more](https://iana.org/domains/example)",
            },
            {
                "role": "assistant",
                "reasoning": "Show the markdown content as is.",
                "content": "# Example Domain\n\nThis domain is for use in documentation examples without needing permission. Avoid use in operations.\n\n[Learn more](https://iana.org/domains/example)",
            },
        ]

        now = datetime.now()
        messages = []
        for i, d in enumerate(message_data):
            created_at = now + timedelta(minutes=i, hours=-1)
            match d["role"]:
                case "user":
                    message = UserMessage(
                        conversation_id=conv_id,
                        created_at=created_at,
                        content=d["content"],
                    )
                case "assistant":
                    message = AssistantMessage(
                        conversation_id=conv_id,
                        created_at=created_at,
                        content=d.get("content", ""),
                        reasoning=d.get("reasoning"),
                        tool_calls=d.get("tool_calls"),
                    )
                case "tool":
                    message = ToolMessage(
                        conversation_id=conv_id,
                        created_at=created_at,
                        content=d["content"],
                        tool_call_id=d["tool_call_id"],
                    )
                case _:
                    raise ValueError(f"Unknown role: {d['role']}")
            messages.append(message)

        await harness.insert_messages(messages)

        assert await harness.count_conversations(user_id) == 1
        assert await harness.count_messages(conv_id) == len(message_data)
        yield conv_id

    @pytest.mark.asyncio
    async def test_create_conversation(self, client: DBClient, harness: DBHarness):
        user_id = 0
        conversation_id = await client.create_conversation(user_id, "Hello World")

        conversation = await harness.fetch_raw_conversation(user_id, conversation_id)
        assert conversation is not None
        assert conversation["user_id"] == user_id
        assert conversation["conversation_id"] == str(conversation_id)
        assert conversation["title"] == "Hello World"

    @pytest.mark.asyncio
    async def test_rename_conversation(self, client: DBClient, harness: DBHarness):
        user_id = 0
        conversation_id = await harness.insert_conversation(user_id, "Old Title")

        conversation = await harness.fetch_raw_conversation(user_id, conversation_id)
        assert conversation is not None
        assert conversation["title"] == "Old Title"

        await client.rename_conversation(user_id, conversation_id, "New Title")

        updated_conversation = await harness.fetch_raw_conversation(
            user_id, conversation_id
        )
        assert updated_conversation is not None
        assert updated_conversation["conversation_id"] == str(conversation_id)
        assert updated_conversation["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_delete_conversation(
        self,
        client: DBClient,
        harness: DBHarness,
        test_conv_id: uuid.UUID,
    ):
        user_id = 0
        await client.delete_conversation(user_id, test_conv_id)

        assert await harness.count_conversations(user_id) == 0
        assert await harness.count_messages(test_conv_id) == 0

    @pytest.mark.asyncio
    async def test_list_conversations(self, client: DBClient, harness: DBHarness):
        user_id = 0
        titles = ["a", "b", "c"]
        for title in titles:
            await harness.insert_conversation(user_id, title)
            await asyncio.sleep(0.001)  # Ensure different timestamps for ordering

        res = await client.list_conversations(user_id)

        assert len(res) == 3
        assert [r.title for r in res] == titles[::-1]

    @pytest.mark.asyncio
    async def test_create_message_user(self, client: DBClient, harness: DBHarness):
        conv_id = uuid.uuid1()

        msg = UserMessage(conversation_id=conv_id, content="User content")
        msg_key = msg.created_at

        await client.create_message(msg)
        stored_user_msg = await harness.fetch_raw_message(conv_id, msg_key)

        assert stored_user_msg is not None
        assert stored_user_msg["role"] == "user"
        assert stored_user_msg["content"] == msg.content

    @pytest.mark.asyncio
    async def test_create_message_assistant_content(
        self, client: DBClient, harness: DBHarness
    ):
        conv_id = uuid.uuid1()

        msg = AssistantMessage(conversation_id=conv_id, content="Assistant content")
        msg_key = msg.created_at

        await client.create_message(msg)
        stored_msg = await harness.fetch_raw_message(conv_id, msg_key)

        assert stored_msg is not None
        assert stored_msg["role"] == "assistant"
        assert stored_msg["content"] == msg.content
        assert "reasoning" not in stored_msg
        assert "tool_calls" not in stored_msg

    @pytest.mark.asyncio
    async def test_create_message_assistant_reasoning_and_tool_calls(
        self, client: DBClient, harness: DBHarness
    ):
        conv_id = uuid.uuid1()

        tool_calls = [
            FunctionToolCall(
                id="call-0",
                function=FunctionToolCall.Function(
                    name="web_scrape", arguments='{"url": "example.com"}'
                ),
            )
        ]
        msg = AssistantMessage(
            conversation_id=conv_id,
            reasoning="Open example.com.",
            tool_calls=tool_calls,
        )
        msg_key = msg.created_at

        await client.create_message(msg)
        stored_msg = await harness.fetch_raw_message(conv_id, msg_key)

        assert stored_msg is not None
        assert stored_msg["role"] == "assistant"
        assert stored_msg["content"] == ""
        assert stored_msg["reasoning"] == msg.reasoning
        assert tool_calls_adapter.validate_json(stored_msg["tool_calls"]) == tool_calls

    @pytest.mark.asyncio
    async def test_create_message_tool(self, client: DBClient, harness: DBHarness):
        conv_id = uuid.uuid1()

        msg = ToolMessage(
            conversation_id=conv_id, content="Example Domain...", tool_call_id="call-0"
        )
        msg_key = msg.created_at

        await client.create_message(msg)
        stored_msg = await harness.fetch_raw_message(conv_id, msg_key)

        assert stored_msg is not None
        assert stored_msg["role"] == "tool"
        assert stored_msg["content"] == msg.content
        assert stored_msg["tool_call_id"] == msg.tool_call_id

    @pytest.mark.asyncio
    async def test_scroll_messages(self, client: DBClient, test_conv_id: uuid.UUID):
        now = datetime.now()
        messages = await client.scroll_messages(test_conv_id, now, limit=100)
        assert len(messages) == 16
        order = [m.created_at for m in messages]
        assert order == sorted(order, reverse=True)

        no_more_messages = await client.scroll_messages(
            test_conv_id, messages[-1].created_at, limit=100
        )
        assert len(no_more_messages) == 0

    @pytest.mark.asyncio
    async def test_load_historical_contents(
        self, client: DBClient, test_conv_id: uuid.UUID
    ):
        messages = await client.load_historical_contents(test_conv_id)
        assert len(messages) == 16
        order = [m.created_at for m in messages]
        assert order == sorted(order)

        assistant_msgs, call_id_2_content = [], {}
        for m in messages:
            if isinstance(m, AssistantMessage):
                assistant_msgs.append(m)
            elif isinstance(m, ToolMessage):
                call_id_2_content[m.tool_call_id] = m.content

        assert len(assistant_msgs) == 8
        assert all(m.reasoning is None for m in assistant_msgs)

        assert len(call_id_2_content) == 4
        assert call_id_2_content["call-0"] == "Array of 1 objects"
        assert call_id_2_content["call-1"] == "4"
        assert call_id_2_content["call-2"] == "Object of 6 keys"
        assert call_id_2_content["call-3"] == "String of 167 chars"


class TestDynamoDBClient(DBClientContract):
    @pytest_asyncio.fixture(scope="class")
    async def testkit(self, dynamodb_testkit: DBTestKit) -> DBTestKit:
        return dynamodb_testkit
