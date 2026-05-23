# Backend

**FastAPI** backend for the chatbot app.

## Architecture Overview

### Key Components

- LLM w/ light-weight web search (**DDGS**) and scrape (**Trafilatura**) tool 
- DB (**DynamoDB**) as conversation state manager
- Streaming end point: streaming LLM responses to client via SSE and persist LLM generated content to DB.

### Notable Design Nuances

- Infrastructure dependencies (LLM, DB) abstracted as `typing.Protocol` to decouple application logics from implementations of the infrastructure layer.
- **OpenAI SDK** as LLM driver. Switching between any LLM provider with OpenAI-compatible endpoints made easy as configuring `base_url` and `api_key`.

## Local Development

Synchorize Python virtual environment and dependencies.

```bash
uv sync
```

### Environment Variables

This project utilizes a `.env` file in backend's root directory to manage environment variables for a variety of tasks, including but not limited to

- Running automated integration tests
- Launch database, and backend dev server

Some of the key variables are ingested by [**Pydantic** settings](api/config.py) and made available to be wired with infrastructure components.

[Here](.env.example) is an example of `.env` file.

### Run Dev Server

First, spin up the DynamoDB local container with tables created using docker compose.

```bash
docker compose up -d
```

Then start the dev server at http://127.0.0.1:8000 by running

```bash
uv run uvicorn api.main:app --reload --env-file .env
```

### Automated Tests

For each component in this app, a proper testing strategy is selected achieve better balance between effectiveness and setup costs.

Run all tests by

```bash
uv run pytest
```

Make sure the [`.env` file](#environment-variables) is properly set so pytest-dotenv plugin can automatically load the variables.

For VSCode TESTING users, add the following setting to make environment variables in `.env` available for its built-in pytest runner.

```json
{
    // using project's root dir as workspace folder
    "python.envFile": "${workspaceFolder}/backend/.env",
}
```

#### LLM

We employ a local LLM running on Ollama for testing. This setting is transferable to an automatic CI pipeline (e.g., Github Actions) without providing additional secrets like an API key.

After installing Ollama, pull the test model first.

```bash
ollama pull qwen3:0.6b
```

Then, run the tests.

```bash
uv run pytest tests/test_infra_llm.py
```

#### Web Search Tool

Tests web search functionality is working or not with a minimal test contract. Run the tests with

```bash
uv run pytest tests/test_infra_tools.py
```

#### Database

Tests specific database implementations for the `DBClient` protocol. We defined another `DBHarness` protocol for handling testing logistics involving database itself, including 

- Table schema creation
- Post test table truncation to isolate each test
- Fixture data prepersisted in the database to test read methods 
- Confirmation of data changes after invoking a write method. 

A unified test contract is developed around the two protocols. For any new `DBClient` implementation, it can be tested against the same contract once its `DBHarnss` is implemented.

To run the tests, first spin up database containers.

```bash
docker compose -f compose.ci.yaml up -d
```

Then, run the tests (with the [`.env` file](#environment-variables) properly set).

```bash
uv run pytest tests/test_infra_db.py
```

#### API Endpoints

Thanks to the decoupled component design, tests against API endpoints are strictly unit tests with infrastructure dependencies mocked. Run them with

```bash
uv run pytest tests/test_main.py
```
