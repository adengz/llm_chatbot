import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.infra.db import ScyllapyClient
from api.infra.llm import OLLAMA_LOCAL_URL, OLLAMA_CLOUD_URL, AsyncLLMClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_client = await ScyllapyClient.create(['localhost:9042'], 'chatbot')
    ollama_cloud_client = AsyncLLMClient(api_key=os.getenv('OLLAMA_API_KEY'), base_url=OLLAMA_CLOUD_URL)
    ollama_local_client = AsyncLLMClient(api_key='ollama', base_url=OLLAMA_LOCAL_URL)
    app.state.db_client = db_client
    app.state.llm_clients = {'ollama_cloud': ollama_cloud_client, 'ollama_local': ollama_local_client}
    yield
    await db_client.close()
