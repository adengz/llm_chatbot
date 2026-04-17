import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.infra.db import AsyncCassandraClient
from api.infra.llm import AsyncLLMAssistant


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_client = await AsyncCassandraClient.create(['localhost'], 'chatbot')
    ollama_cloud_client = AsyncLLMAssistant(api_key=os.getenv('OLLAMA_API_KEY'), base_url='https://ollama.com/v1')
    ollama_local_client = AsyncLLMAssistant(api_key='ollama', base_url='http://localhost:11434/v1')
    app.state.db_client = db_client
    app.state.llm_clients = {'ollama_cloud': ollama_cloud_client, 'ollama_local': ollama_local_client}
    yield
    await db_client.session.close()
