import uuid
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from api.main import app, get_db
from api.infra.db import AsyncCassandraClient
from api.domain.models import Conversation, Message, Role


@pytest.fixture
def api_ut_toolkit():
    # 1. Create the mock
    mock_db = AsyncMock(AsyncCassandraClient)
    
    # 2. Tell FastAPI: "Whenever someone asks for get_db, give them mock_db"
    app.dependency_overrides[get_db] = lambda: mock_db
    
    # 3. Create the client WITHOUT the 'with' block 
    # (Since we are overriding the dependency, we don't need the lifespan to run)
    yield TestClient(app), mock_db
    
    # 4. Clean up the override after the test
    app.dependency_overrides.clear()


class TestAppEndpoints:

    def test_create_message(self, api_ut_toolkit):
        client, mock_db = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conversation_id
        
        response = client.post('/messages', json={
            'role': 'user',
            'content': 'Hello, world!',
            'conversation_id': None
        })
        
        assert response.status_code == 200
        body = response.json()
        assert body['conversation_id'] == str(conversation_id)
        assert body['role'] == 'assistant'
        assert body['content'] == 'This is a response from the AI assistant.'

        mock_db.create_conversation.assert_awaited_once_with(user_id=0, title='Hello, world!')
        assert mock_db.create_message.await_count == 2

        first_call_message = mock_db.create_message.await_args_list[0].kwargs['message']
        second_call_message = mock_db.create_message.await_args_list[1].kwargs['message']

        assert str(first_call_message.conversation_id) == str(conversation_id)
        assert first_call_message.role == 'user'
        assert first_call_message.content == 'Hello, world!'

        assert str(second_call_message.conversation_id) == str(conversation_id)
        assert second_call_message.role == 'assistant'
        assert second_call_message.content == 'This is a response from the AI assistant.'

    def test_create_message_invalid_role(self, api_ut_toolkit):
        client, _ = api_ut_toolkit
        
        response = client.post('/messages', json={
            'role': 'assistant',
            'content': 'Hello from the other side',
            'conversation_id': None
        })
        
        assert response.status_code == 400

    def test_list_conversations(self, api_ut_toolkit):
        client, mock_db = api_ut_toolkit
        
        mock_db.list_conversations.return_value = [
            Conversation(conversation_id=uuid.uuid1(), user_id=0, title='Conversation'),
            Conversation(conversation_id=uuid.uuid1(), user_id=0, title='Another conversation'),
            Conversation(conversation_id=uuid.uuid1(), user_id=0, title='Yet another conversation'),
        ]
        
        response = client.get('/conversations')
        
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        assert [c['title'] for c in body] == ['Conversation', 'Another conversation', 'Yet another conversation']
        mock_db.list_conversations.assert_awaited_once_with(user_id=0)

    def test_list_messages(self, api_ut_toolkit):
        client, mock_db = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        
        mock_db.list_messages.return_value = [
            Message(conversation_id=conversation_id, role=Role.ASSISTANT, content='Hi there!'),
            Message(conversation_id=conversation_id, role=Role.USER, content='Hello'),
        ]
        
        response = client.get(f'/conversations/{conversation_id}/messages')
        
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert [m['role'] for m in body] == ['assistant', 'user']
        assert [m['content'] for m in body] == ['Hi there!', 'Hello']

        assert mock_db.list_messages.await_count == 1
        assert mock_db.list_messages.await_args.kwargs['conversation_id'] == conversation_id
        assert mock_db.list_messages.await_args.kwargs['limit'] == 2
        assert mock_db.list_messages.await_args.kwargs['cursor'] is not None

    def test_delete_conversation(self, api_ut_toolkit):
        client, mock_db = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        
        response = client.delete(f'/conversations/{conversation_id}')
        
        assert response.status_code == 200
        mock_db.delete_conversation.assert_awaited_once_with(user_id=0, conversation_id=conversation_id)

    def test_rename_conversation(self, api_ut_toolkit):
        client, mock_db = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        new_title = 'New Conversation Title'
        
        response = client.patch(f'/conversations/{conversation_id}', json={'title': new_title})
        
        assert response.status_code == 200
        mock_db.rename_conversation.assert_awaited_once_with(user_id=0, conversation_id=conversation_id,
                                                             new_title=new_title)
    