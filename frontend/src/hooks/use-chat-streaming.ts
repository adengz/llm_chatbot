import { useRef, useState, type Dispatch, type SetStateAction } from 'react'

import { streamMessage } from '../client/stream'
import type { ChatMessage, ModelSource, ToolCall } from '../components/chat-types'

const STREAMING_MESSAGE_ID = '__streaming__'

type SendMessageArgs = {
  content: string
  conversationId: string | null
  modelSource: ModelSource
  model: string
  webAccess: boolean
}

type UseChatStreamingParams = {
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>
  setMessagesError: Dispatch<SetStateAction<string | null>>
  onMetadata: (conversationId: string, startedFromNewConversation: boolean) => void
}

type UseChatStreamingResult = {
  isStreaming: boolean
  sendMessage: (args: SendMessageArgs) => boolean
  stopStreaming: () => void
}

export function useChatStreaming({
  setMessages,
  setMessagesError,
  onMetadata,
}: UseChatStreamingParams): UseChatStreamingResult {
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const parseToolCallArguments = (argumentsRaw: unknown): unknown => {
    if (typeof argumentsRaw !== 'string') {
      return argumentsRaw
    }

    try {
      return JSON.parse(argumentsRaw)
    } catch {
      return argumentsRaw
    }
  }

  const parseToolCalls = (raw: unknown): ToolCall[] | undefined => {
    let payload = raw
    if (typeof payload === 'string') {
      try {
        payload = JSON.parse(payload)
      } catch {
        return undefined
      }
    }

    if (!Array.isArray(payload)) {
      return undefined
    }

    const toolCalls: ToolCall[] = []
    for (const item of payload) {
      if (!item || typeof item !== 'object') {
        continue
      }

      const record = item as {
        id?: unknown
        function?: { name?: unknown; arguments?: unknown }
      }

      if (typeof record.id !== 'string') {
        continue
      }

      if (!record.function || typeof record.function.name !== 'string') {
        continue
      }

      toolCalls.push({
        id: record.id,
        function: {
          name: record.function.name,
          arguments: parseToolCallArguments(record.function.arguments),
        },
      })
    }

    return toolCalls.length > 0 ? toolCalls : undefined
  }

  const parseToolContent = (raw: unknown): unknown => {
    if (typeof raw !== 'string') {
      return raw ?? ''
    }

    const trimmed = raw.trim()
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        return JSON.parse(trimmed)
      } catch {
        return raw
      }
    }

    return raw
  }

  const createFinalId = (role: ChatMessage['role']) => `${role}-${Date.now()}-${Math.random()}`

  const stopStreaming = () => {
    abortRef.current?.abort()
  }

  const finalizeStreamingMessages = (fallbackAssistantContent?: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id.startsWith(STREAMING_MESSAGE_ID)
          ? m.role === 'assistant'
            ? {
                ...m,
                id: createFinalId(m.role),
                content: m.content || fallbackAssistantContent || '',
              }
            : {
                ...m,
                id: createFinalId(m.role),
              }
          : m,
      ),
    )
  }

  const finalizeMessageById = (messageId: string | null) => {
    if (!messageId) {
      return
    }

    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, id: createFinalId(m.role) } : m)),
    )
  }

  const sendMessage = ({
    content,
    conversationId,
    model,
    webAccess,
  }: SendMessageArgs): boolean => {
    const trimmed = content.trim()
    if (!trimmed || isStreaming) {
      return false
    }

    const startedFromNewConversation = !conversationId

    setIsStreaming(true)
    setMessagesError(null)

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
    }

    setMessages((prev) => [...prev, userMessage])

    const abort = new AbortController()
    abortRef.current = abort

    void (async () => {
      try {
        let currentAssistantId: string | null = null

        const ensureCurrentAssistant = () => {
          if (currentAssistantId) {
            return currentAssistantId
          }

          currentAssistantId = `${STREAMING_MESSAGE_ID}-assistant-${Date.now()}-${Math.random()}`
          const assistantMessage: ChatMessage = {
            id: currentAssistantId,
            role: 'assistant',
            content: '',
          }
          setMessages((prev) => [...prev, assistantMessage])
          return currentAssistantId
        }

        for await (const event of streamMessage(
          {
            conversation_id: conversationId ?? undefined,
            content: trimmed,
            model,
            web_access: webAccess,
          },
          abort.signal,
        )) {
          if (event.type === 'metadata') {
            onMetadata(event.conversation_id, startedFromNewConversation)
            continue
          }

          if (event.type === 'reasoning') {
            const assistantId = ensureCurrentAssistant()
            if (!event.delta) {
              continue
            }

            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId || m.role !== 'assistant') {
                  return m
                }
                return {
                  ...m,
                  reasoning: `${m.reasoning ?? ''}${event.delta}`,
                }
              }),
            )
            continue
          }

          if (event.type === 'content') {
            const assistantId = ensureCurrentAssistant()
            if (!event.delta) {
              continue
            }

            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId || m.role !== 'assistant') {
                  return m
                }
                return {
                  ...m,
                  content: m.content + event.delta,
                }
              }),
            )
            continue
          }

          if (event.type === 'tool_calls') {
            const assistantId = ensureCurrentAssistant()
            const nextToolCalls = parseToolCalls(event.data)

            if (nextToolCalls) {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId || m.role !== 'assistant') {
                    return m
                  }
                  return {
                    ...m,
                    toolCalls: nextToolCalls,
                  }
                }),
              )
            }

            finalizeMessageById(assistantId)
            currentAssistantId = null
            continue
          }

          if (event.type === 'tool') {
            const toolMessage: ChatMessage = {
              id: `tool-${event.tool_call_id}-${Date.now()}-${Math.random()}`,
              role: 'tool',
              toolCallId: event.tool_call_id,
              content: parseToolContent(event.data),
            }
            setMessages((prev) => [...prev, toolMessage])
            continue
          } else if (event.type === 'error') {
            setMessagesError(event.exception)
            finalizeStreamingMessages(`[Error: ${event.exception}]`)
          } else if (event.type === 'done') {
            finalizeStreamingMessages()
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setMessagesError((err as Error).message)
          finalizeStreamingMessages('[Error: stream failed]')
        } else {
          finalizeStreamingMessages()
        }
      } finally {
        abortRef.current = null
        setIsStreaming(false)
      }
    })()

    return true
  }

  return {
    isStreaming,
    sendMessage,
    stopStreaming,
  }
}
