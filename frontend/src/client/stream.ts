import type { MessageRequest } from './types.gen'
import { API_BASE_URL } from '../config'
import { createSseClient } from './core/serverSentEvents.gen'

export type SSEEvent =
  | { type: 'metadata'; conversation_id: string }
  | { type: 'reasoning'; delta: string }
  | { type: 'tool_calls'; data?: unknown }
  | { type: 'tool'; tool_call_id: string; data?: unknown }
  | { type: 'content'; delta: string }
  | { type: 'error'; exception: string }
  | { type: 'done' }

const SSE_EVENT_TYPES = new Set([
  'metadata',
  'reasoning',
  'tool_calls',
  'tool',
  'content',
  'error',
  'done',
])

function isSSEEvent(value: unknown): value is SSEEvent {
  if (!value || typeof value !== 'object') {
    return false
  }

  const maybeType = (value as { type?: unknown }).type
  return typeof maybeType === 'string' && SSE_EVENT_TYPES.has(maybeType)
}

export async function* streamMessage(
  req: MessageRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const { stream } = createSseClient({
    url: `${API_BASE_URL}/messages`,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    serializedBody: JSON.stringify(req),
    signal,
    onSseError: (error) => {
      if (error instanceof Error) {
        throw error
      }
      throw new Error(String(error))
    },
  })

  for await (const rawEvent of stream) {
    if (!isSSEEvent(rawEvent)) {
      continue
    }

    yield rawEvent

    if (rawEvent.type === 'done' || rawEvent.type === 'error') {
      return
    }
  }
}
