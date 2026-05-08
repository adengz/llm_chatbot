FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY ./pyproject.toml ./uv.lock /app

RUN uv sync --locked --no-dev

COPY ./api /app/api

CMD ["uv", "run", "fastapi", "run", "api/main.py", "--port", "80"]