# Backend

FastAPI + Python backend for the chatbot app.

## Local Development

Install dependencies:

```bash
uv sync
```

Start Scylla and initialize schema:

```bash
docker compose up -d --wait
```

Run API server:

```bash
uv run fastapi dev api/main.py
```

## Quality Checks

Run tests once:

```bash
uv run pytest
```

Run tests with coverage:

```bash
uv run pytest --cov=api --cov-report=term-missing
```

## CI

GitHub Actions runs backend checks in parallel with frontend checks using:

1. `docker compose up -d --wait`
2. `uv sync --frozen`
3. `uv run pytest --cov=api --cov-report=term-missing`
4. `docker compose down`

The workflow is defined in `.github/workflows/ci.yml`.
