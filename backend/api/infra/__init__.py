from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.infra.db import AsyncCassandraClient

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_client = await AsyncCassandraClient.create(['localhost'], 'chatbot')
    app.state.db_client = db_client
    yield
    await db_client.session.close()
