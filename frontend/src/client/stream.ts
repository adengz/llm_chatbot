import type { MessageRequest } from './types.gen'
import { API_BASE_URL } from '../config'

export type SSEEvent =
  | { type: 'metadata'; conversation_id: string }
  | { type: 'reasoning'; delta: string }
  | { type: 'content'; delta: string }
  | { type: 'done' }

export async function* streamMessage(
  req: MessageRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE_URL}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    throw new Error(`POST /messages failed: ${response.status} ${text}`)
  }

  if (!response.body) {
    throw new Error('Response body is empty')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        const payload = trimmed.slice(5).trim()
        if (!payload) continue

        let event: SSEEvent
        try {
          event = JSON.parse(payload) as SSEEvent
        } catch {
          continue
        }

        yield event

        if (event.type === 'done') return
      }
    }
  } finally {
    reader.releaseLock()
  }
}
