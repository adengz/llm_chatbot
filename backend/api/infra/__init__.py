from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.infra.db import ScyllapyClient
from api.infra.llm import AsyncOllamaClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_client = await ScyllapyClient.create(['localhost:9042'], 'chatbot')
    app.state.db_client = db_client
    app.state.llm_client = AsyncOllamaClient(use_cloud=True)
    yield
    await db_client.close()
