import uuid
import json
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from api.main import app, get_db, get_llm
from api.infra.db import AsyncCassandraClient
from api.domain.models import ReasoningEffort, Message, Role, Conversation


@pytest.fixture
def api_ut_toolkit():
    mock_db = AsyncMock(AsyncCassandraClient)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_llm] = lambda: None

    yield TestClient(app), mock_db

    app.dependency_overrides.clear()


class LLMWithFixedResponse:

    def __init__(self, reasoning_tokens: list[str], content_tokens: list[str]):
        self.calls = []
        self.reasoning_tokens = reasoning_tokens
        self.content_tokens = content_tokens

    async def stream_response(self, messages: list[Message], model: str, reasoning_effort: ReasoningEffort):
        self.calls.append({
            'messages': messages,
            'model': model,
            'reasoning_effort': reasoning_effort,
        })
        for token in self.reasoning_tokens:
            yield 'reasoning', token
        for token in self.content_tokens:
            yield 'content', token


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split('\n\n'):
        if not block:
            continue
        assert block.startswith('data: ')
        payload = block.removeprefix('data: ')
        events.append(json.loads(payload))
    return events


class TestAppEndpoints:

    def test_create_message_new_conversation(self, api_ut_toolkit):
        client, mock_db = api_ut_toolkit

        reasoning_tokens = ['Oh', ' my', ' fucking', ' god', '!', ' It\'s',' Trevor', ' Philips', '...']
        content_tokens = ['Trevor', '?']
        fake_llm = LLMWithFixedResponse(reasoning_tokens=reasoning_tokens, content_tokens=content_tokens)
        app.dependency_overrides[get_llm] = lambda: fake_llm

        conversation_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conversation_id
        
        message = 'Somebody say yoga?'
        model = 'michaael-de-santa'
        reasoning_effort = 'high'

        response = client.post('/messages', json={
            'content': message,
            'conversation_id': None,
            'model': model,
            'reasoning_effort': reasoning_effort,
        })

        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')

        events = parse_sse_events(response.text)
        assert len(events) == len(reasoning_tokens) + len(content_tokens) + 2
        assert events[0] == {'type': 'metadata', 'conversation_id': str(conversation_id)}
        assert events[-1] == {'type': 'done'}
        for event, token in zip(events[1:1 + len(reasoning_tokens)], reasoning_tokens):
            assert event == {'type': 'reasoning', 'delta': token}
        for event, token in zip(events[1 + len(reasoning_tokens):-1], content_tokens):
            assert event == {'type': 'content', 'delta': token}        

        mock_db.create_conversation.assert_awaited_once_with(user_id=0, title=message)
        mock_db.list_messages.assert_not_awaited()
        assert mock_db.create_message.await_count == 2

        first_call_message = mock_db.create_message.await_args_list[0].kwargs['message']
        second_call_message = mock_db.create_message.await_args_list[1].kwargs['message']

        assert str(first_call_message.conversation_id) == str(conversation_id)
        assert first_call_message.role == Role.USER
        assert first_call_message.content == message

        assert str(second_call_message.conversation_id) == str(conversation_id)
        assert second_call_message.role == Role.ASSISTANT
        assert second_call_message.content == ''.join(content_tokens)

        assert len(fake_llm.calls) == 1
        assert fake_llm.calls[0]['model'] == model
        assert fake_llm.calls[0]['reasoning_effort'] == reasoning_effort
        assert len(fake_llm.calls[0]['messages']) == 1
        assert fake_llm.calls[0]['messages'][0].content == message

    def test_create_message_existing_conversation_with_history(self, api_ut_toolkit):
        client, mock_db = api_ut_toolkit     

        reasoning_tokens = ['WTF', '...']
        content_tokens = ['Hey', '...', ' It\'s', ' good', ' to', ' see', ' you', ',', ' man', '.']
        fake_llm = LLMWithFixedResponse(reasoning_tokens=reasoning_tokens, content_tokens=content_tokens)
        app.dependency_overrides[get_llm] = lambda: fake_llm

        conversation_id = uuid.uuid1()
        history_messages = [
            Message(conversation_id=conversation_id, role=Role.ASSISTANT, content='Trevor?'),
            Message(conversation_id=conversation_id, role=Role.USER, content='Somebody say yoga?'),
        ]
        mock_db.list_messages.side_effect = [history_messages, []]

        message = 'Michael...'
        model = 'michaael-de-santa'
        reasoning_effort = 'low'

        response = client.post('/messages', json={
            'content': message,
            'conversation_id': str(conversation_id),
            'model': model,
            'reasoning_effort': reasoning_effort,
        })

        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')

        events = parse_sse_events(response.text)
        assert len(events) == len(reasoning_tokens) + len(content_tokens) + 2
        assert events[0] == {'type': 'metadata', 'conversation_id': str(conversation_id)}
        assert events[-1] == {'type': 'done'}
        for event, token in zip(events[1:1 + len(reasoning_tokens)], reasoning_tokens):
            assert event == {'type': 'reasoning', 'delta': token}
        for event, token in zip(events[1 + len(reasoning_tokens):-1], content_tokens):
            assert event == {'type': 'content', 'delta': token}  

        mock_db.create_conversation.assert_not_awaited()
        assert mock_db.list_messages.await_count == 2
        assert mock_db.list_messages.await_args_list[0].kwargs['conversation_id'] == conversation_id
        assert mock_db.list_messages.await_args_list[0].kwargs['limit'] == 100
        assert mock_db.create_message.await_count == 2

        first_call_message = mock_db.create_message.await_args_list[0].kwargs['message']
        second_call_message = mock_db.create_message.await_args_list[1].kwargs['message']

        assert str(first_call_message.conversation_id) == str(conversation_id)
        assert first_call_message.role == Role.USER
        assert first_call_message.content == message

        assert str(second_call_message.conversation_id) == str(conversation_id)
        assert second_call_message.role == Role.ASSISTANT
        assert second_call_message.content == ''.join(content_tokens)

        assert len(fake_llm.calls) == 1
        assert fake_llm.calls[0]['model'] == model
        assert fake_llm.calls[0]['reasoning_effort'] == reasoning_effort
        assert len(fake_llm.calls[0]['messages']) == 3
        assert [m.content for m in fake_llm.calls[0]['messages']] == [message, 'Trevor?', 'Somebody say yoga?']

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
    