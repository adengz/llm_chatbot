import datetime
import json
import uuid
from contextlib import asynccontextmanager

import aioboto3
from boto3.dynamodb.conditions import Key
from loguru import logger
from pydantic import TypeAdapter

from api.domain.models import (
    AssistantMessage,
    Conversation,
    FunctionToolCall,
    Message,
    ToolMessage,
    UserMessage,
)

tool_calls_adapter = TypeAdapter(list[FunctionToolCall])


class DynamoDBClient:
    def __init__(
        self,
        endpoint_url: str | None = None,
        conversations_table: str = "conversations",
        messages_table: str = "messages",
    ):
        self.session = aioboto3.Session()
        self._aws_endpoint_url = endpoint_url
        self._conversations_table = conversations_table
        self._messages_table = messages_table

    @asynccontextmanager
    async def get_resource(self):
        async with self.session.resource(
            "dynamodb", endpoint_url=self._aws_endpoint_url
        ) as resource:
            yield resource

    async def create_conversation(self, user_id: int, title: str) -> uuid.UUID:
        conversation_id = uuid.uuid7()
        item = {
            "user_id": user_id,
            "conversation_id": str(conversation_id),
            "title": title,
        }
        async with self.get_resource() as resource:
            table = await resource.Table(self._conversations_table)
            await table.put_item(Item=item)
        return conversation_id

    async def rename_conversation(
        self, user_id: int, conversation_id: uuid.UUID, new_title: str
    ) -> None:
        async with self.get_resource() as resource:
            table = await resource.Table(self._conversations_table)
            await table.update_item(
                Key={"user_id": user_id, "conversation_id": str(conversation_id)},
                UpdateExpression="SET #title = :new_title",
                ExpressionAttributeNames={"#title": "title"},
                ExpressionAttributeValues={":new_title": new_title},
            )

    async def delete_conversation(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> None:
        query_params = {
            "KeyConditionExpression": Key("conversation_id").eq(str(conversation_id)),
        }
        keys = await self._list_items(self._messages_table, query_params)
        async with self.get_resource() as resource:
            table = await resource.Table(self._messages_table)
            async with table.batch_writer() as batch:
                for key in keys:
                    await batch.delete_item(
                        Key={
                            "conversation_id": key["conversation_id"],
                            "created_at": key["created_at"],
                        }
                    )

            table = await resource.Table(self._conversations_table)
            await table.delete_item(
                Key={"user_id": user_id, "conversation_id": str(conversation_id)},
            )

    async def list_conversations(self, user_id: int) -> list[Conversation]:
        query_params = {
            "KeyConditionExpression": Key("user_id").eq(user_id),
            "ScanIndexForward": False,
        }
        items = await self._list_items(self._conversations_table, query_params)
        return [
            Conversation(
                user_id=user_id,
                conversation_id=uuid.UUID(item["conversation_id"]),
                title=item["title"],
            )
            for item in items
        ]

    async def create_message(self, message: Message) -> None:
        created_at = message.created_at.isoformat()
        item = {
            "conversation_id": str(message.conversation_id),
            "created_at": created_at,
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

        async with self.get_resource() as resource:
            table = await resource.Table(self._messages_table)
            await table.put_item(Item=item)

    async def scroll_messages(
        self,
        conversation_id: uuid.UUID,
        cursor: datetime.datetime,
        limit: int = 100,
    ) -> list[Message]:
        query_params = {
            "KeyConditionExpression": Key("conversation_id").eq(str(conversation_id))
            & Key("created_at").lt(cursor.isoformat()),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        items = await self._list_items(self._messages_table, query_params)
        return self._pack_messages(items)

    async def load_historical_contents(
        self, conversation_id: uuid.UUID
    ) -> list[Message]:
        query_params = {
            "KeyConditionExpression": Key("conversation_id").eq(str(conversation_id)),
            "ScanIndexForward": True,
        }
        items = await self._list_items(self._messages_table, query_params)
        return self._pack_messages(items, context_filter=True)

    async def _list_items(self, table_name: str, query_params: dict) -> list[dict]:
        all_items = []
        limit = query_params.get("Limit", 0)
        async with self.get_resource() as resource:
            table = await resource.Table(table_name)
            while True:
                response = await table.query(**query_params)
                all_items.extend(response.get("Items", []))
                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key or (limit and len(all_items) >= limit):
                    break
                query_params["ExclusiveStartKey"] = last_evaluated_key
        if limit:
            all_items = all_items[:limit]
        return all_items

    @staticmethod
    def _pack_messages(
        items: list[dict], context_filter: bool = False
    ) -> list[Message]:
        messages = []
        for item in items:
            conversation_id = uuid.UUID(item["conversation_id"])
            created_at = datetime.datetime.fromisoformat(item["created_at"])
            content = item["content"]
            match item["role"]:
                case "user":
                    message = UserMessage(
                        conversation_id=conversation_id,
                        created_at=created_at,
                        content=content,
                    )
                case "assistant":
                    tool_calls = None
                    tc = item.get("tool_calls")
                    if tc is not None:
                        tool_calls = tool_calls_adapter.validate_json(tc)
                    message = AssistantMessage(
                        conversation_id=conversation_id,
                        created_at=created_at,
                        content=content,
                        reasoning=item.get("reasoning") if not context_filter else None,
                        tool_calls=tool_calls,
                    )
                case "tool":
                    message = ToolMessage(
                        conversation_id=conversation_id,
                        created_at=created_at,
                        content=_compress_tool_content(content)
                        if context_filter
                        else content,
                        tool_call_id=item["tool_call_id"],
                    )
                case _:
                    logger.warning(f"Unknown message role: {item['role']}")
                    continue
            messages.append(message)
        return messages


def _compress_tool_content(content: str) -> str:
    try:
        obj = json.loads(content)
        if isinstance(obj, list):
            return f"Array of {len(obj)} objects"
        elif isinstance(obj, dict):
            return f"Object of {len(obj)} keys"
        else:
            return content
    except json.JSONDecodeError:
        return f"String of {len(content)} chars"
