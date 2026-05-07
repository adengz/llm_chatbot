import datetime
import uuid
from contextlib import asynccontextmanager
from typing import Literal, cast

import aioboto3
from boto3.dynamodb.conditions import Key

from api.domain.models import Conversation, Message


class DatabaseException(Exception):
    pass


class DynamoDBClient:
    def __init__(self, use_local: bool = False):
        self.session = aioboto3.Session()
        self.use_local = use_local

    @asynccontextmanager
    async def get_resource(self):
        endpoint_url = "http://localhost:8000" if self.use_local else None
        try:
            async with self.session.resource(
                "dynamodb", endpoint_url=endpoint_url
            ) as resource:
                yield resource
        except Exception as e:
            raise DatabaseException("Failed to get DynamoDB resource") from e

    async def create_conversation(self, user_id: int, title: str) -> uuid.UUID:
        conversation_id = uuid.uuid7()
        item = {
            "user_id": user_id,
            "conversation_id": str(conversation_id),
            "title": title,
        }
        async with self.get_resource() as resource:
            table = await resource.Table("conversations")
            await table.put_item(Item=item)
        return conversation_id

    async def rename_conversation(
        self, user_id: int, conversation_id: uuid.UUID, new_title: str
    ) -> None:
        async with self.get_resource() as resource:
            table = await resource.Table("conversations")
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
        keys = await self._list_items("messages", query_params)
        async with self.get_resource() as resource:
            table = await resource.Table("messages")
            async with table.batch_writer() as batch:
                for key in keys:
                    await batch.delete_item(
                        Key={
                            "conversation_id": key["conversation_id"],
                            "created_at": key["created_at"],
                        }
                    )

            table = await resource.Table("conversations")
            await table.delete_item(
                Key={"user_id": user_id, "conversation_id": str(conversation_id)},
            )

    async def list_conversations(self, user_id: int) -> list[Conversation]:
        query_params = {
            "KeyConditionExpression": Key("user_id").eq(user_id),
            "ScanIndexForward": False,
        }
        items = await self._list_items("conversations", query_params)
        return [
            Conversation(
                user_id=user_id,
                conversation_id=uuid.UUID(item["conversation_id"]),
                title=item["title"],
            )
            for item in items
        ]

    async def create_message(self, message: Message) -> None:
        item = {
            "conversation_id": str(message.conversation_id),
            "created_at": message.created_at.isoformat(),
            "role": message.role,
            "type": message.type,
            "content": message.content,
        }
        async with self.get_resource() as resource:
            table = await resource.Table("messages")
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
        items = await self._list_items("messages", query_params)
        return self._pack_messages(items)

    async def load_historical_contents(
        self, conversation_id: uuid.UUID
    ) -> list[Message]:
        query_params = {
            "IndexName": "type-created_at-idx",
            "KeyConditionExpression": Key("conversation_id").eq(str(conversation_id))
            & Key("type-created_at").begins_with("content#"),
            "ScanIndexForward": False,
        }
        all_keys = await self._list_items("messages", query_params)
        offset = 0
        all_items = []
        async with self.get_resource() as resource:
            while offset < len(all_keys):
                keys = all_keys[offset : offset + 100]
                response = await resource.batch_get_item(
                    RequestItems={
                        "messages": {
                            "Keys": [
                                {
                                    "conversation_id": key["conversation_id"],
                                    "created_at": key["created_at"],
                                }
                                for key in keys
                            ]
                        }
                    }
                )
                all_items.extend(response.get("Responses", {}).get("messages", []))
                offset += 100

        return self._pack_messages(all_items)

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
    def _pack_messages(items: list[dict]) -> list[Message]:
        return [
            Message(
                conversation_id=uuid.UUID(item["conversation_id"]),
                created_at=datetime.datetime.fromisoformat(item["created_at"]),
                role=cast(Literal["user", "assistant"], item["role"]),
                type=cast(
                    Literal["tool_call_req", "tool_call_resp", "thinking", "content"],
                    item["type"],
                ),
                content=item["content"],
            )
            for item in items
        ]
