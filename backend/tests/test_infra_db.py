import uuid
import asyncio

import pytest

from api.domain.models import Message, Role


class TestAsyncCassandraClient:

    async def _create_conversation(self, db_client, user_id: int = 0, title: str = '') -> uuid.UUID:
        conversation_id = uuid.uuid1()
        query = await db_client.session.prepare('INSERT INTO conversations (user_id, conversation_id, title) '
                                               'VALUES (?, ?, ?)')
        await db_client.session.execute(query, (user_id, conversation_id, title))
        return conversation_id

    @pytest.mark.asyncio
    async def test_create_conversation(self, db_client):
        user_id = 0
        title = 'Hello World'
        conversation_id = await db_client.create_conversation(user_id, title)

        query = await db_client.session.prepare('SELECT title FROM conversations '
                                                'WHERE user_id = ? AND conversation_id = ?')
        res = await db_client.session.execute(query, (user_id, conversation_id))
        
        assert len(res) == 1
        assert res[0].title == title

    @pytest.mark.asyncio
    async def test_rename_conversation(self, db_client):
        user_id = 0
        conversation_id = await self._create_conversation(db_client, user_id=user_id)

        new_title = 'New Title'
        await db_client.rename_conversation(user_id, conversation_id, new_title)

        query = await db_client.session.prepare('SELECT title FROM conversations '
                                                'WHERE user_id = ? AND conversation_id = ?')
        res = await db_client.session.execute(query, (user_id, conversation_id))
        
        assert len(res) == 1
        assert res[0].title == new_title

    @pytest.mark.asyncio
    async def test_delete_conversation(self, db_client):
        user_id = 0
        conversation_id = await self._create_conversation(db_client, user_id=user_id)

        await db_client.delete_conversation(user_id, conversation_id)

        query = await db_client.session.prepare('SELECT COUNT(1) FROM conversations '
                                                'WHERE user_id = ? AND conversation_id = ?')
        res = await db_client.session.execute(query, (user_id, conversation_id))
        
        assert res[0].count == 0

    @pytest.mark.asyncio
    async def test_list_conversations(self, db_client):
        user_id = 0
        titles = ['a', 'b', 'c']
        for title in titles:
            await self._create_conversation(db_client, user_id=user_id, title=title)
            await asyncio.sleep(0.001)  # Ensure different timestamps for ordering
        
        res = await db_client.list_conversations(user_id)

        assert len(res) == 3
        assert [r.title for r in res] == titles[::-1]

    @pytest.mark.asyncio
    async def test_create_message(self, db_client):
        conversation_id = uuid.uuid1()
        role = Role.USER
        content = 'Hello World'
        message = Message(conversation_id=conversation_id, role=role, content=content)

        created_at = await db_client.create_message(message)
        query = await db_client.session.prepare('SELECT role, content FROM messages '
                                                'WHERE conversation_id = ? AND created_at = ?')
        res = await db_client.session.execute(query, (conversation_id, created_at))
        
        assert len(res) == 1
        assert res[0].role == role.value
        assert res[0].content == content

    @pytest.mark.asyncio
    async def test_list_messages(self, db_client):
        conversation_id = uuid.uuid1()
        from datetime import datetime, timedelta
        now = datetime.now()
        messages_data = [
            (now - timedelta(minutes=1), Role.ASSISTANT.value, '4'),
            (now - timedelta(minutes=2), Role.USER.value, '2+2=?'),
            (now - timedelta(minutes=3), Role.ASSISTANT.value, '2'),
            (now - timedelta(minutes=4), Role.USER.value, '1+1=?'),
        ]
        
        query = await db_client.session.prepare('INSERT INTO messages (conversation_id, created_at, role, content) '
                                               'VALUES (?, ?, ?, ?)')
        for created_at, role, content in messages_data:
            await db_client.session.execute(query, (conversation_id, created_at, role, content))
        
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
