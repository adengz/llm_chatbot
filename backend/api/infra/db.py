import datetime
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal, Self, cast

import aioboto3
from scyllapy import PreparedQuery, QueryResult, Scylla, extra_types

from api.domain.models import Conversation, Message
from api.infra.exceptions import DatabaseException


class ScyllapyClient:
    def __init__(self, scylla: Scylla):
        self.scylla = scylla
        self._prepared_statements = {}

    @classmethod
    async def create(
        cls, contact_points: list[str], keyspace: str | None = None
    ) -> Self:
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
        try:
            prepared = await self._prepare(query)
            return await self.scylla.execute(prepared, parameters)
        except Exception as exc:
            raise DatabaseException("Database operation failed") from exc

    async def create_conversation(self, user_id: int, title: str) -> uuid.UUID:
        conversation_id = uuid.uuid1()
        await self._execute_prepared(
            "INSERT INTO conversations (user_id, conversation_id, title) VALUES (?, ?, ?)",
            [extra_types.BigInt(user_id), conversation_id, title],
        )
        return conversation_id

    async def rename_conversation(
        self, user_id: int, conversation_id: uuid.UUID, new_title: str
    ) -> None:
        await self._execute_prepared(
            "UPDATE conversations SET title = ? WHERE user_id = ? AND conversation_id = ?",
            [new_title, extra_types.BigInt(user_id), conversation_id],
        )

    async def delete_conversation(
        self, user_id: int, conversation_id: uuid.UUID
    ) -> None:
        await self._execute_prepared(
            "DELETE FROM messages WHERE conversation_id = ?",
            [conversation_id],
        )
        await self._execute_prepared(
            "DELETE FROM conversations WHERE user_id = ? AND conversation_id = ?",
            [extra_types.BigInt(user_id), conversation_id],
        )

    async def list_conversations(self, user_id: int) -> list[Conversation]:
        result = await self._execute_prepared(
            "SELECT conversation_id, title FROM conversations WHERE user_id = ?",
            [extra_types.BigInt(user_id)],
        )
        return [
            Conversation(
                user_id=user_id,
                conversation_id=row["conversation_id"],
                title=row["title"],
            )
            for row in result.all()
        ]

    async def create_message(self, message: Message) -> None:
        await self._execute_prepared(
            "INSERT INTO messages (conversation_id, created_at, role, type, content) VALUES (?, ?, ?, ?, ?)",
            [
                message.conversation_id,
                message.created_at,
                message.role,
                message.type,
                message.content,
            ],
        )

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        cursor: datetime.datetime,
        limit: int = 2,
        content_only: bool = False,
    ) -> list[Message]:
        wheres = ["conversation_id = ?", "created_at < ?"]
        parameters = [conversation_id, cursor]
        if content_only:
            wheres.append("type = ?")
            parameters.append("content")
        parameters.append(limit)

        result = await self._execute_prepared(
            f"SELECT created_at, role, type, content FROM messages WHERE {' AND '.join(wheres)} LIMIT ?",
            parameters,
        )
        return [
            Message(
                conversation_id=conversation_id,
                created_at=row["created_at"],
                role=row["role"],
                type=row["type"],
                content=row["content"],
            )
            for row in result.all()
        ]


class DynamoDBClient:
    def __init__(self, use_local: bool = False):
        self.session = aioboto3.Session()
        self.use_local = use_local

    @asynccontextmanager
    async def get_resource(self):
        endpoint_url = "http://localhost:8000" if self.use_local else None
        async with self.session.resource(
            "dynamodb", endpoint_url=endpoint_url
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
            "KeyConditionExpression": "#conversation_id = :conversation_id",
            "ProjectionExpression": "#conversation_id, #created_at",
            "ExpressionAttributeNames": {
                "#conversation_id": "conversation_id",
                "#created_at": "created_at",
            },
            "ExpressionAttributeValues": {
                ":conversation_id": str(conversation_id),
            },
        }
        items = await self._list_items("messages", query_params)
        async with self.get_resource() as resource:
            table = await resource.Table("messages")
            async with table.batch_writer() as batch:
                for item in items:
                    await batch.delete_item(
                        Key={
                            "conversation_id": item["conversation_id"],
                            "created_at": item["created_at"],
                        }
                    )

            table = await resource.Table("conversations")
            await table.delete_item(
                Key={"user_id": user_id, "conversation_id": str(conversation_id)},
            )

    async def list_conversations(self, user_id: int) -> list[Conversation]:
        query_params = {
            "KeyConditionExpression": "#user_id = :user_id",
            "ExpressionAttributeNames": {"#user_id": "user_id"},
            "ExpressionAttributeValues": {":user_id": user_id},
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

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        cursor: datetime.datetime,
        limit: int = 2,
        content_only: bool = False,
    ) -> list[Message]:
        query_params = {
            "ScanIndexForward": False,
            "Limit": limit,
            "KeyConditionExpression": "#conversation_id = :conversation_id",
            "ExpressionAttributeNames": {"#conversation_id": "conversation_id"},
            "ExpressionAttributeValues": {":conversation_id": str(conversation_id)},
        }
        if content_only:
            query_params["IndexName"] = "type-created_at-idx"
            query_params["KeyConditionExpression"] += (
                " AND #type_created_at BETWEEN :start AND :end"
            )
            query_params["ExpressionAttributeNames"]["#type_created_at"] = (
                "type-created_at"
            )
            query_params["ExpressionAttributeValues"][":start"] = "content#"
            query_params["ExpressionAttributeValues"][":end"] = (
                "content#" + cursor.isoformat()
            )
        else:
            query_params["KeyConditionExpression"] += " AND #created_at < :cursor"
            query_params["ExpressionAttributeNames"]["#created_at"] = "created_at"
            query_params["ExpressionAttributeValues"][":cursor"] = cursor.isoformat()

        items = await self._list_items("messages", query_params)
        print(items)
        return [
            Message(
                conversation_id=conversation_id,
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
