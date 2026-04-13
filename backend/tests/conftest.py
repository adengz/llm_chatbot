import sys
from pathlib import Path


# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


import pytest_asyncio
from api.infra.db import AsyncCassandraClient


@pytest_asyncio.fixture(scope='session')
async def db_client():
    client = await AsyncCassandraClient.create(['localhost'], 'chatbot')
    yield client
    

@pytest_asyncio.fixture(autouse=True)
async def truncate_tables(db_client):
    yield
    await db_client.session.execute('TRUNCATE chatbot.conversations')
    await db_client.session.execute('TRUNCATE chatbot.messages')
