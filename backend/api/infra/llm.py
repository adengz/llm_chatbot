import os
from collections import deque
from typing import AsyncGenerator

from ollama import AsyncClient, web_search, web_fetch, ResponseError

from api.domain.models import Message, AgentStreamChunk

OLLAMA_LOCAL_HOST = 'http://localhost:11434'
OLLAMA_CLOUD_HOST = 'https://ollama.com'


class AsyncOllamaClient:
    
    def __init__(self, use_cloud: bool = False):        
        if use_cloud:
            OLLAMA_API_KEY = os.environ['OLLAMA_API_KEY']
            self.client = AsyncClient(host=OLLAMA_CLOUD_HOST, headers={'Authorization': 'Bearer ' + OLLAMA_API_KEY})
        else:
            self.client = AsyncClient()

    async def list_models(self) -> list[str]:
        response = await self.client.list()
        return sorted([m['model'] for m in response['models']])
    
    async def stream_response(self, context: list[Message], model: str, web_access: bool = False) \
        -> AsyncGenerator[AgentStreamChunk, None]:
        messages = [m.model_dump(include=['role', 'content']) for m in reversed(context)]
        tools = [web_search, web_fetch] if web_access else None
        done = False
        tool_calls = deque()

        try:
            while tool_calls or not done:
                while tool_calls:
                    tool_call = tool_calls.popleft()
                    yield AgentStreamChunk(type='tool_call_req', data=tool_call.function)
                    func = getattr(self.client, tool_call.function.name)
                    response = await func(**tool_call.function.arguments)
                    yield AgentStreamChunk(type='tool_call_resp', data=response)
                    new_message = {'role': 'tool', 'tool_name': tool_call.function.name}
                    new_message['content'] = response.model_dump_json()
                    messages.append(new_message)

                async for part in await self.client.chat(
                    model=model, 
                    messages=messages, 
                    tools=tools, 
                    stream=True, 
                    think=True,
                ):
                    if part.message.tool_calls is not None:
                        tool_calls.extend(part.message.tool_calls)
                    elif part.message.thinking is not None:
                        yield AgentStreamChunk(type='thinking', delta=part.message.thinking)
                    elif part.message.content:
                        yield AgentStreamChunk(type='content', delta=part.message.content)
                    done = part.done

            yield AgentStreamChunk(type='done')

        except ResponseError as exc:
            yield AgentStreamChunk(type='error', exception=exc.error, status_code=exc.status_code)
        except Exception as exc:
            yield AgentStreamChunk(type='error', exception=str(exc), status_code=500)
    