import { useRef, useState, type Dispatch, type SetStateAction } from 'react'

import { streamMessage } from '../client/stream'
import type { ChatMessage, ModelSource, ReasoningEffort } from '../components/chat-types'

const STREAMING_MESSAGE_ID = '__streaming__'

type SendMessageArgs = {
  content: string
  conversationId: string | null
  modelSource: ModelSource
  model: string
  reasoningEffort: ReasoningEffort
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

  const stopStreaming = () => {
    abortRef.current?.abort()
  }

  const finalizeStreamingMessage = (fallbackContent?: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === STREAMING_MESSAGE_ID
          ? { ...m, id: `assistant-${Date.now()}`, content: m.content || fallbackContent || '' }
          : m,
      ),
    )
  }

  const sendMessage = ({
    content,
    conversationId,
    modelSource,
    model,
    reasoningEffort,
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

    const streamingMessage: ChatMessage = {
      id: STREAMING_MESSAGE_ID,
      role: 'assistant',
      content: '',
    }

    setMessages((prev) => [...prev, userMessage, streamingMessage])

    const abort = new AbortController()
    abortRef.current = abort

    void (async () => {
      try {
        for await (const event of streamMessage(
          {
            conversation_id: conversationId ?? undefined,
            content: trimmed,
            model_source: modelSource,
            model,
            reasoning_effort: reasoningEffort,
          },
          abort.signal,
        )) {
          if (event.type === 'metadata') {
            onMetadata(event.conversation_id, startedFromNewConversation)
          } else if (event.type === 'content') {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === STREAMING_MESSAGE_ID ? { ...m, content: m.content + event.delta } : m,
              ),
            )
          } else if (event.type === 'reasoning') {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === STREAMING_MESSAGE_ID
                  ? { ...m, reasoning: (m.reasoning ?? '') + event.delta }
                  : m,
              ),
            )
          } else if (event.type === 'error') {
            setMessagesError(event.exception)
            finalizeStreamingMessage(`[Error: ${event.exception}]`)
          } else if (event.type === 'done') {
            finalizeStreamingMessage()
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setMessagesError((err as Error).message)
          finalizeStreamingMessage('[Error: stream failed]')
        } else {
          finalizeStreamingMessage()
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
