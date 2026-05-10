# Backend

FastAPI + Python backend for the chatbot app.

## Architecture Overview

### Key Components

- LLM (Ollama) w/ web search and fetch tool 
- DB (DynamoDB) as conversation state manager
- Streaming end point: streaming LLM responses to client via SSE and persist LLM generated content to DB.

### Notable Design Nuances

- Infrastructure dependencies (LLM, DB) abstracted as `typing.Protocol` to decouple application logics from implementations of the infrastructure layer.
- Strictly isolated error handling for infrastructure components. For instance, DB errors during LLM streaming will only generate a warning event to notify client without interrupting the stream.

## Local Development

Synchorize Python virtual environment and dependencies.

```bash
uv sync
```

### Ollama LLM Integration

Both Ollama cloud models and web search tool (powered by Ollama) require an API key. First, signup and create an API key. Then, set the `OLLAMA_API_KEY` environment variable to your API key.

```bash
export OLLAMA_API_KEY=your_api_key
```

Cloud models generally have much larger context window than those hosted locally. This makes them more capable for handling long web search results.

### DynamoDB Integration

We use a DynamoDB local container to integrate DynamoDB without directly connecting to AWS. First, create an `.env` file with the following variables.

```
# Consumed by aioboto3 SDK, pointing to the DynamoDB local container
AWS_ENDPOINT_URL="http://localhost:8000"

# Dummy AWS configurations, not required if you have configured at ~/.aws
AWS_DEFAULT_REGION="not-on-earth"
AWS_ACCESS_KEY_ID="NotAnAccessKeyId"
AWS_SECRET_ACCESS_KEY="not+a+secret+access+key"

# Required by compose.yaml for creating DynamoDB tables
DYNAMODB_CONVERSATIONS_TABLE="conversations"
DYNAMODB_MESSAGES_TABLE="messages"
DYNAMODB_ENDPOINT="http://dynamodb-local:8000"
```

Then, spin up the DynamoDB local container with docker compose.

```bash
docker compose up -d
```

### Run Dev Server

With DynamoDB local container properly wired, we may start the dev server by running

```bash
uv run uvicorn api.main:app --reload --env-file .env
```

Failure in DynamoDB local will not crash the server instantly, but only fail requests with DB read or write.

## Automated Tests

### LLM

We employ a local LLM for testing. After installing Ollama, pull the test model first.

```bash
ollama pull qwen3:0.6b
```
Then, run the tests.

```bash
uv run pytest tests/test_infra_llm.py
```
Note that web search tool in the tests is mocked, so Ollama API key is not required.

### Database

Tests specific database implementations for the `DBClient` protocol. We defined another `DBHarness` protocol for handling testing logistics involving database itself, including 
- Table schema creation
- Post test table truncation to isolate each test
- Fixture data prepersisted in the database to test read methods 
- Confirmation of data changes after invoking a write method. 

A unified test contract is developed around the two protocols. For any new `DBClient` implementation, it can be tested against the same contract once its `DBHarnss` is implemented.

To run the tests, first spin up database containers.

```bash
docker compose -f compose_ci.yaml up -d
```

Then, run the tests. For DynamoDB, [make sure the `.env` file is properly set](#dynamodb-integration).

```bash
uv run pytest tests/test_infra_db.py
```

### API Endpoints

Thanks to the decoupled component design, tests against API endpoints are strictly unit tests with infrastructure dependencies mocked. Run them with

```bash
uv run pytest tests/test_main.py
```
