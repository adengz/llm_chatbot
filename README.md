# Full Stack LLM Chatbot

A full-stack LLM chatbot application featuring a React frontend, Python FastAPI backend, and DynamoDB for persistence.

## Project Structure

- `frontend/`: React application with Vite, Tailwind CSS, and Shadcn UI.
- `backend/`: FastAPI application with Pydantic settings and OpenAI SDK integration.
- `compose.yaml`: Main Docker Compose file to orchestrate the whole stack.

## Prerequisites

- [Docker](https://www.docker.com/get-started) and Docker Compose installed.
- A `.env` file in the root directory (see [Other Environment Variables](#other-environment-variables)).

## Run the Application Locally

### Environment Variables

#### LLM API Key

Using [Ollama Cloud](https://docs.ollama.com/cloud#cloud-api-access) as an example LLM provider. You may use any provider with OpenAI-compatible endpoints. 

Create an API key, then set an environment variable to this key.

```bash
export OLLAMA_API_KEY=your_api_key
```
This key will be injected to backend container via docker compose as a secret.

#### Other Environment Variables

Consumed by multiple containers defined in [`compose.yaml`](compose.yaml). A working example of `.env` file can be found [here](.env.example). 

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

