import uuid
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fastapi.testclient import TestClient

from api.main import app, get_db, get_llms, get_disconnect_checker, DBClient
from api.domain.models import ReasoningEffort, Message, Role, Conversation


@pytest.fixture
def api_ut_toolkit():
    mock_db = AsyncMock(DBClient)
    llm_clients = {}

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_llms] = lambda: llm_clients

    yield TestClient(app), mock_db, llm_clients

    app.dependency_overrides.clear()


class ModelLister:

    def __init__(self, models: list[str], ex: Exception | None = None):
        self.calls = 0
        self.models = models
        self.ex = ex

    async def list_models(self) -> list[str]:
        self.calls += 1
        if self.ex is not None:
            raise self.ex
        return self.models
    

class Stream:

    def __init__(self, chunks: list[SimpleNamespace], ex: Exception | None = None):
        self._chunks = chunks
        self._index = 0
        self._ex = ex
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index < len(self._chunks):
            chunk = self._chunks[self._index]
            self._index += 1
            return chunk
        if self._ex is not None:
            ex = self._ex
            self._ex = None
            raise ex
        raise StopAsyncIteration

    async def close(self):
        self.closed = True


class ResponseStreamer:

    def __init__(self, reasoning_tokens: list[str], content_tokens: list[str], ex: Exception | None = None):
        self.calls = []
        self.reasoning_tokens = reasoning_tokens
        self.content_tokens = content_tokens
        self.ex = ex
        self.last_stream = None

    @staticmethod
    def _chunk(reasoning: str | None = None, content: str | None = None, finish_reason: str | None = None) -> SimpleNamespace:
        if reasoning is not None:
            delta = SimpleNamespace(reasoning=reasoning, content=None)
        elif content is not None:
            delta = SimpleNamespace(content=content)
        else:
            delta = SimpleNamespace(content=None)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])

    async def stream_response(self, context: list[Message], model: str, reasoning_effort: ReasoningEffort):
        self.calls.append({
            'messages': context,
            'model': model,
            'reasoning_effort': reasoning_effort,
        })
        chunks = []
        chunks.extend([self._chunk(reasoning=token) for token in self.reasoning_tokens])
        chunks.extend([self._chunk(content=token) for token in self.content_tokens])
        chunks.append(self._chunk(finish_reason='stop'))
        self.last_stream = Stream(chunks=chunks, ex=self.ex)
        return self.last_stream


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

    def test_list_llms_all_available(self, api_ut_toolkit):
        client, _, llm_clients = api_ut_toolkit

        local_models = ['michael-de-santa', 'trevor-philips']
        cloud_models = ['claude']
        llm_clients['lifeinvader_local'] = ModelLister(models=local_models)
        llm_clients['lifeinvader_cloud'] = ModelLister(models=cloud_models)

        response = client.get('/models')

        assert response.status_code == 200
        assert response.json() == {
            'lifeinvader_local': local_models,
            'lifeinvader_cloud': cloud_models,
        }
        assert llm_clients['lifeinvader_local'].calls == 1
        assert llm_clients['lifeinvader_cloud'].calls == 1

    def test_list_llms_skips_unavailable_sources(self, api_ut_toolkit):
        client, _, llm_clients = api_ut_toolkit

        llm_clients['lifeinvader_local'] = ModelLister(models=['michael-de-santa', 'trevor-philips'])
        llm_clients['lifeinvader_cloud'] = ModelLister(models=[], ex=RuntimeError('service unavailable'))

        response = client.get('/models')

        assert response.status_code == 200
        assert response.json() == {
            'lifeinvader_local': ['michael-de-santa', 'trevor-philips'],
        }
        assert llm_clients['lifeinvader_local'].calls == 1
        assert llm_clients['lifeinvader_cloud'].calls == 1

    def test_create_message_unsupported_model_source(self, api_ut_toolkit):
        client, mock_db, _ = api_ut_toolkit

        unsupported_source = 'lifeinvader'
        response = client.post('/messages', json={
            'content': 'Jay Norris?',
            'conversation_id': None,
            'model_source': unsupported_source,
            'model': 'jay-norris',
            'reasoning_effort': 'medium',
        })

        assert response.status_code == 400
        mock_db.create_conversation.assert_not_awaited()
        mock_db.list_messages.assert_not_awaited()
        mock_db.create_message.assert_not_awaited()

    def test_create_message_new_conversation(self, api_ut_toolkit):
        client, mock_db, llm_clients = api_ut_toolkit

        reasoning_tokens = ['Oh', ' my', ' fucking', ' god', '!', ' It\'s',' Trevor', ' Philips', '...']
        content_tokens = ['Trevor', '?']
        fake_llm = ResponseStreamer(reasoning_tokens=reasoning_tokens, content_tokens=content_tokens)
        model_source = 'lifeinvader_cloud'
        llm_clients[model_source] = fake_llm

        conversation_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conversation_id
        
        message = 'Somebody say yoga?'
        model = 'michael-de-santa'
        reasoning_effort = 'high'

        response = client.post('/messages', json={
            'content': message,
            'conversation_id': None,
            'model_source': model_source,
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
        client, mock_db, llm_clients = api_ut_toolkit

        reasoning_tokens = ['WTF', '...']
        content_tokens = ['Hey', '...', ' It\'s', ' good', ' to', ' see', ' you', ',', ' man', '.']
        fake_llm = ResponseStreamer(reasoning_tokens=reasoning_tokens, content_tokens=content_tokens)
        model_source = 'ollama_local'
        llm_clients[model_source] = fake_llm

        conversation_id = uuid.uuid1()
        history_messages = [
            Message(conversation_id=conversation_id, role=Role.ASSISTANT, content='Trevor?'),
            Message(conversation_id=conversation_id, role=Role.USER, content='Somebody say yoga?'),
        ]
        mock_db.list_messages.side_effect = [history_messages, []]

        message = 'Michael...'
        model = 'michael-de-santa'
        reasoning_effort = 'low'

        response = client.post('/messages', json={
            'content': message,
            'conversation_id': str(conversation_id),
            'model_source': model_source,
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

    def test_create_message_disconnect_mid_stream(self, api_ut_toolkit):
        client, mock_db, llm_clients = api_ut_toolkit

        async def disconnect_after_first_chunk() -> bool:
            disconnect_after_first_chunk.calls += 1
            return disconnect_after_first_chunk.calls >= 2

        disconnect_after_first_chunk.calls = 0
        app.dependency_overrides[get_disconnect_checker] = lambda: disconnect_after_first_chunk

        reasoning_tokens = ['...']
        content_tokens = ['Woof']
        fake_llm = ResponseStreamer(reasoning_tokens=reasoning_tokens, content_tokens=content_tokens)
        model_source = 'lifeinvader_local'
        llm_clients[model_source] = fake_llm

        conversation_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conversation_id

        response = client.post('/messages', json={
            'content': '',
            'conversation_id': None,
            'model_source': model_source,
            'model': 'chop'
        })

        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')

        events = parse_sse_events(response.text)
        assert events == [
            {'type': 'metadata', 'conversation_id': str(conversation_id)},
            {'type': 'reasoning', 'delta': '...'},
        ]

        assert disconnect_after_first_chunk.calls == 2
        assert fake_llm.last_stream is not None
        assert fake_llm.last_stream.closed is True

        assert mock_db.create_message.await_count == 1

    def test_create_message_llm_error_during_streaming(self, api_ut_toolkit):
        client, mock_db, llm_clients = api_ut_toolkit

        reasoning_tokens = ['...']
        content_tokens = ['Woof']
        llm_error = RuntimeError('stream failed')
        fake_llm = ResponseStreamer(reasoning_tokens=reasoning_tokens, content_tokens=content_tokens, ex=llm_error)
        model_source = 'lifeinvader_local'
        llm_clients[model_source] = fake_llm

        conversation_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conversation_id

        response = client.post('/messages', json={
            'content': '',
            'conversation_id': None,
            'model_source': model_source,
            'model': 'chop',
        })

        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')

        events = parse_sse_events(response.text)
        assert events[0] == {'type': 'metadata', 'conversation_id': str(conversation_id)}
        assert events[-1] == {'type': 'error', 'exception': str(llm_error)}
        assert not any(event['type'] == 'done' for event in events)

        assert fake_llm.last_stream is not None
        assert fake_llm.last_stream.closed is True

        assert mock_db.create_message.await_count == 1

    def test_list_conversations(self, api_ut_toolkit):
        client, mock_db, _ = api_ut_toolkit
        
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
        client, mock_db, _ = api_ut_toolkit
        
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
        client, mock_db, _ = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        
        response = client.delete(f'/conversations/{conversation_id}')
        
        assert response.status_code == 200
        mock_db.delete_conversation.assert_awaited_once_with(user_id=0, conversation_id=conversation_id)

    def test_rename_conversation(self, api_ut_toolkit):
        client, mock_db, _ = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        new_title = 'New Conversation Title'
        
        response = client.patch(f'/conversations/{conversation_id}', json={'title': new_title})
        
        assert response.status_code == 200
        mock_db.rename_conversation.assert_awaited_once_with(user_id=0, conversation_id=conversation_id,
                                                             new_title=new_title)
    