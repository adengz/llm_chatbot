# Frontend

React + TypeScript + Vite frontend for the chatbot app.

## Local Development

Install dependencies:

```bash
npm install
```

Run dev server:

```bash
npm run dev
```

### Environment Variables

The frontend can be configured using environment variables. Create a `.env` file in the `frontend` directory:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Quality Checks

Run lint:

```bash
npm run lint
```

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

Build production bundle:

```bash
npm run build
```

## CI

GitHub Actions runs frontend checks in parallel with backend checks using:

1. `npm ci`
2. `npm run lint`
3. `npm run test:coverage`
4. `npm run build`

The workflow is defined in `.github/workflows/ci.yml`.
