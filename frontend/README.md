# Frontend

React + TypeScript + Vite frontend for the chatbot app.

## Architecture Overview

The frontend is a **Single Page Application (SPA)** built with **React** and **TypeScript**, leveraging **Vite** for optimized builds. It follows a **Custom Hook Pattern** for state management, where domain logic (streaming, history, etc.) is decoupled from UI components. Real-time communication is achieved via **Server-Sent Events (SSE)** for streaming LLM responses.

### Key Components

- **`use-chat-streaming`**: Orchestrates the SSE message flow, handling incremental updates and state transitions.
- **`use-conversations`**: Manages the list of past conversations (CRUD operations).
- **`use-chat-scroll`**: Handles complex scroll behaviors like auto-scroll and scroll anchoring.
- **`ChatModule`**: The main orchestrator component that integrates domain hooks to manage the chat lifetime.

### Notable Design Nuances

- **SSE Streaming**: Instead of standard WebSockets, the app uses a custom `fetch`-based SSE implementation to handle streaming tokens, thinking states, and tool call updates.
- **Auto-Generated SDK**: The REST client is partially generated from the backend's OpenAPI schema, ensuring type synchronization between frontend and backend.
- **Rich Message Rendering**: Support for GitHub Flavored Markdown (GFM) and specialized components for visualizing internal LLM thought processes and tool interaction JSON.

## Local Development

Install dependencies:

```bash
npm install
```

### Environment Variables

The frontend can be configured using environment variables. Create a `.env` file in the `frontend` directory:

```env
VITE_API_BASE_URL=http://localhost:8000
```

### Run Dev Server

With the backend running and the `.env` file configured, start the development server:

```bash
npm run dev
```

The app will be available at `http://localhost:5173`. Any changes to the source code will trigger a hot reload.

## Quality Checks

Run linting with ESLint:

```bash
npm run lint
```

### Automated Tests

We use **Vitest** and **React Testing Library** for frontend testing. Tests cover business logic in hooks and component interactions, with heavy use of mocking for API and streaming responses.

Run tests once:

```bash
npm run test
```

Run tests in watch mode:

```bash
npm run test:watch
```

Run tests with coverage:

```bash
npm run test:coverage
```

### Build

Create a production-ready bundle:

```bash
npm run build
```

The output will be in the `dist/` directory.
