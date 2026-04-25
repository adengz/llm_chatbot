import uuid
import json
from typing import Literal, AsyncGenerator

import pytest
from unittest.mock import AsyncMock, MagicMock

from pydantic import create_model, BaseModel
from fastapi.testclient import TestClient

from api.main import DBClient, LLMClient, app, get_db, get_llm, get_disconnect_checker
from api.domain.models import Message, Conversation, AgentStreamChunk
from api.infra.exceptions import DatabaseException


def tokenize(text: str) -> list[str]:
    return [w if i == 0 else ' ' + w for i, w in enumerate(text.split())]


MockWebSearchRequest = create_model('MockWebSearchRequest', query=str, max_results=(int, 3))
MockWebSearchResult = create_model('MockWebSearchResult', content=str, title=str)
MockWebSearchResponse = create_model('MockWebSearchResponse', results=(list[MockWebSearchResult], ...))


class MockLLMStreamer:

    def __init__(
            self, 
            responses: list[
                tuple[Literal['thinking', 'tool_call_req', 'tool_call_resp', 'content'], str | BaseModel]
            ],
        ):
        self.chunks = []
        for tp, data in responses:
            if tp in ['thinking', 'content']:
                for delta in tokenize(data):
                    self.chunks.append(AgentStreamChunk(type=tp, delta=delta))
            else:
                self.chunks.append(AgentStreamChunk(type=tp, data=data))

    async def stream_response(self, *args, **kwargs) -> AsyncGenerator[AgentStreamChunk, None]:
        for chunk in self.chunks:
            yield chunk
        yield AgentStreamChunk(type='done')


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split('\n\n'):
        if not block:
            continue
        assert block.startswith('data: ')
        payload = block.removeprefix('data: ')
        events.append(json.loads(payload))
    return events


@pytest.fixture
def api_ut_toolkit():
    mock_db = AsyncMock(DBClient)
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.stream_response = MagicMock()  # Initialize as MagicMock for call tracking
    mock_disconnect = AsyncMock(return_value=False)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_llm] = lambda: mock_llm
    app.dependency_overrides[get_disconnect_checker] = lambda: mock_disconnect

    yield TestClient(app), mock_db, mock_llm, mock_disconnect

    app.dependency_overrides.clear()


class TestAppEndpoints:

    def test_list_models(self, api_ut_toolkit):
        client, _, mock_llm, _ = api_ut_toolkit

        models = ['claude', 'gemini', 'gpt']
        mock_llm.list_models.return_value = models

        response = client.get('/models')

        assert response.status_code == 200
        assert response.json() == models
        mock_llm.list_models.assert_awaited_once()

    def test_create_message_new_conversation(self, api_ut_toolkit):
        client, mock_db, mock_llm, _ = api_ut_toolkit
        
        conv_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conv_id

        llm_responses = [
            ('thinking', 'Need to respond friendly.'),
            ('content', 'Hi there! 👋 How can I help you today?'),
        ]
        streamer = MockLLMStreamer(responses=llm_responses)
        mock_llm.stream_response.side_effect = streamer.stream_response

        payload = {'content': 'Hello', 'model': 'test-model', 'web_access': False}
        response = client.post('/messages', json=payload)
        
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        
        assert len(events) == 1 + len(streamer.chunks) + 1
        assert events[0]['type'] == 'metadata'
        assert events[0]['conversation_id'] == str(conv_id)
        assert events[-1]['type'] == 'done'
        
        assert mock_llm.stream_response.call_count == 1
        _, kwargs = mock_llm.stream_response.call_args
        assert kwargs['model'] == payload['model']
        assert kwargs['web_access'] == payload['web_access']
        context = kwargs['context']
        assert len(context) == 1
        assert context[0].role == 'user'
        assert context[0].content == payload['content']

        assert mock_db.create_message.await_count == 1 + len(llm_responses)
        user_msg = mock_db.create_message.await_args_list[0].kwargs['message']
        assert user_msg.conversation_id == conv_id
        assert user_msg.role == 'user'
        assert user_msg.type == 'content'
        assert user_msg.content == payload['content']
        for i, (tp, data) in enumerate(llm_responses):
            bot_msg = mock_db.create_message.await_args_list[i + 1].kwargs['message']
            assert bot_msg.conversation_id == conv_id
            assert bot_msg.role == 'assistant'
            assert bot_msg.type == tp
            match tp:
                case 'thinking' | 'content':
                    assert bot_msg.content == data
                case 'tool_call_req' | 'tool_call_resp':
                    assert bot_msg.content == data.dump_model_json()

    def test_create_message_existing_conversation(self, api_ut_toolkit):
        client, mock_db, mock_llm, _ = api_ut_toolkit
        
        conv_id = uuid.uuid1()
        existing_msgs = [
            Message(conversation_id=conv_id, role='assistant', content='Hi there! 👋 How can I help you today?'),
            Message(conversation_id=conv_id, role='user', content='Hello'),
        ]
        mock_db.list_messages.side_effect = [existing_msgs, []]

        mock_web_search_req = MockWebSearchRequest(query='Current price of Bitcoin in USD?', max_results=1)
        mock_web_search_resp = MockWebSearchResponse(results=[MockWebSearchResult(
			content='$50,000 USD',
			title='Bitcoin Price'
		)])
        
        llm_responses = [
            ('thinking', 'Need current price. browse.'),
            ('tool_call_req', mock_web_search_req),
            ('tool_call_resp', mock_web_search_resp),
            ('thinking', 'Got the price. Need to format response.'),
            ('content', 'The current price of Bitcoin is $50,000 USD.'),
        ]
        streamer = MockLLMStreamer(responses=llm_responses)
        mock_llm.stream_response.side_effect = streamer.stream_response

        payload = {'content': 'Current price of Bitcoin in USD?', 'model': 'test-model', 'web_access': True}
        payload['conversation_id'] = str(conv_id)
        response = client.post('/messages', json=payload)
        
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        
        assert len(events) == 1 + len(streamer.chunks) + 1
        assert events[-1]['type'] == 'done'
        
        assert mock_llm.stream_response.call_count == 1
        _, kwargs = mock_llm.stream_response.call_args
        assert kwargs['model'] == payload['model']
        assert kwargs['web_access'] == payload['web_access']
        context = kwargs['context']
        assert len(context) == 1 + len(existing_msgs)
        assert context[0].role == 'user'
        assert context[0].content == payload['content']
        assert context[1:] == existing_msgs

        assert mock_db.create_message.await_count == 1 + len(llm_responses)
        user_msg = mock_db.create_message.await_args_list[0].kwargs['message']
        assert user_msg.conversation_id == conv_id
        assert user_msg.role == 'user'
        assert user_msg.type == 'content'
        assert user_msg.content == payload['content']
        for i, (tp, data) in enumerate(llm_responses):
            bot_msg = mock_db.create_message.await_args_list[i + 1].kwargs['message']
            assert bot_msg.conversation_id == conv_id
            assert bot_msg.role == 'assistant'
            assert bot_msg.type == tp
            match tp:
                case 'thinking' | 'content':
                    assert bot_msg.content == data
                case 'tool_call_req' | 'tool_call_resp':
                    assert bot_msg.content == data.model_dump_json()

    def test_create_message_client_disconnect(self, api_ut_toolkit):
        client, mock_db, mock_llm, mock_disconnect = api_ut_toolkit
        
        conv_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conv_id

        # Disconnect after exactly 1 iteration (1st chunk)
        mock_disconnect.side_effect = [True]

        llm_responses = [
            ('thinking', 'Need to respond friendly.'),
            ('content', 'Hi there! 👋 How can I help you today?'),
        ]
        streamer = MockLLMStreamer(responses=llm_responses)
        mock_llm.stream_response.side_effect = streamer.stream_response    

        payload = {'content': 'Hello', 'model': 'test-model', 'web_access': False}
        response = client.post('/messages', json=payload)
        
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        
        assert len(events) == 1 + 1
        assert events[-1]['type'] == llm_responses[0][0]
        expected_content = tokenize(llm_responses[0][1])[0]
        assert events[-1]['delta'] == expected_content
        
        assert mock_db.create_message.await_count == 2
        bot_msg = mock_db.create_message.await_args_list[1].kwargs['message']
        assert bot_msg.role == 'assistant'
        assert bot_msg.type == llm_responses[0][0]
        assert bot_msg.content == expected_content

    def test_create_message_db_failure_during_stream(self, api_ut_toolkit):
        client, mock_db, mock_llm, _ = api_ut_toolkit
        
        conv_id = uuid.uuid1()
        mock_db.create_conversation.return_value = conv_id

        # Simulate DB failure on create_message for the assistant messages
        # 1st call from user message (succeeds), subsequent calls from bot (fail)
        db_exp = Exception('DB Down')
        mock_db.create_message.side_effect = [None, db_exp, db_exp]

        llm_responses = [
            ('thinking', 'Need to respond friendly.'),
            ('content', 'Hi there! 👋 How can I help you today?'),
        ]
        streamer = MockLLMStreamer(responses=llm_responses)
        mock_llm.stream_response.side_effect = streamer.stream_response    

        payload = {'content': 'Hello', 'model': 'test-model', 'web_access': False}
        response = client.post('/messages', json=payload)
        
        assert response.status_code == 200
        events = parse_sse_events(response.text)

        assert len(events) == 1 + len(streamer.chunks) + 1 + len(llm_responses)
        assert events[-1]['type'] == 'done'
        thinking_tokens, content_tokens, warnings = [], [], 0
        for event in events[1:-1]:
            match event['type']:
                case 'thinking':
                    thinking_tokens.append(event['delta'])
                case 'content':
                    content_tokens.append(event['delta'])
                case 'warning':
                    warnings += 1
        
        assert ''.join(thinking_tokens) == llm_responses[0][1]
        assert ''.join(content_tokens) == llm_responses[1][1]
        assert warnings == 2

    def test_db_exception_handler(self, api_ut_toolkit):
        client, mock_db, mock_llm, _ = api_ut_toolkit
        
        why = 'DB Down'
        mock_db.create_message.side_effect = DatabaseException(why)
        
        payload = {'content': 'Hello', 'model': 'test-model', 'web_access': False}
        response = client.post('/messages', json=payload)
        
        assert response.status_code == 500
        assert response.json() == {'detail': why}

        assert mock_llm.stream_response.never_awaited()

    def test_list_conversations(self, api_ut_toolkit):
        client, mock_db, _, _ = api_ut_toolkit
        
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
        client, mock_db, _, _ = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        
        mock_db.list_messages.return_value = [
            Message(conversation_id=conversation_id, role='assistant', content='Hi there!'),
            Message(conversation_id=conversation_id, role='user', content='Hello'),
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
        assert mock_db.list_messages.await_args.kwargs.get('content_only', False) is False

    def test_delete_conversation(self, api_ut_toolkit):
        client, mock_db, _, _ = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        
        response = client.delete(f'/conversations/{conversation_id}')
        
        assert response.status_code == 200
        mock_db.delete_conversation.assert_awaited_once_with(user_id=0, conversation_id=conversation_id)

    def test_rename_conversation(self, api_ut_toolkit):
        client, mock_db, _, _ = api_ut_toolkit
        
        conversation_id = uuid.uuid1()
        new_title = 'New Conversation Title'
        
        response = client.patch(f'/conversations/{conversation_id}', json={'title': new_title})
        
        assert response.status_code == 200
        mock_db.rename_conversation.assert_awaited_once_with(user_id=0, conversation_id=conversation_id,
                                                             new_title=new_title)
    