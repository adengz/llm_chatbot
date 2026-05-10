# Full Stack LLM Chatbot

A full-stack LLM chatbot application featuring a React frontend, Python FastAPI backend, and DynamoDB for persistence.

## Project Structure

- `frontend/`: React application with Vite, Tailwind CSS, and Shadcn UI.
- `backend/`: FastAPI application with Pydantic settings and Ollama integration.
- `compose.yaml`: Main Docker Compose file to orchestrate the whole stack.

## Prerequisites

- [Docker](https://www.docker.com/get-started) and Docker Compose installed.
- An `.env` file in the root directory (see [Environment Variables](#environment-variables)).

## Run the application locally

### Environment Variables

Create an `.env` file in the root folder with the following variables:

```env
# AWS / DynamoDB local configs
# Consumed by aioboto3 SDK, pointing to the DynamoDB local container
AWS_ENDPOINT_URL="http://dynamodb-local:8000"
# Dummy AWS configurations, not required if you have configured at ~/.aws
AWS_DEFAULT_REGION="not-on-earth"
AWS_ACCESS_KEY_ID="NotAnAccessKeyId"
AWS_SECRET_ACCESS_KEY="not+a+secret+access+key"
# DynamoDB table names used
DYNAMODB_CONVERSATIONS_TABLE="conversations"
DYNAMODB_MESSAGES_TABLE="messages"

# Ollama api key to use cloud model and web search
OLLAMA_API_KEY=your_api_key_here

# Nginx config for routing requests to backend
BACKEND_URL="http://backend/"
```
### Spin up the entire stack

To spin up the full stack including the frontend, backend, and a local DynamoDB instance, run:

```bash
docker compose up -d --build
```

The application will be available at [http://localhost:3000](http://localhost:3000).

## Development

For more details, refer to the document in each sub project

- [Backend](backend/README.md)
- [Frontend](frontend/README.md)

