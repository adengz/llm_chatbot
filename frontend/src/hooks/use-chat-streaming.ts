import { useRef, useState, type Dispatch, type SetStateAction } from 'react'

import { streamMessage } from '../client/stream'
import type { ChatMessage, ModelSource } from '../components/chat-types'

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

  const stopStreaming = () => {
    abortRef.current?.abort()
  }

  const finalizeStreamingMessage = (fallbackContent?: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id.startsWith(STREAMING_MESSAGE_ID)
          ? { ...m, id: `${m.type}-${Date.now()}-${Math.random()}`, content: m.content || fallbackContent || '' }
          : m,
      ),
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
        let currentStreamingId: string | null = null
        let currentSegmentType: string | null = null

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
          } else if (
            event.type === 'thinking' ||
            event.type === 'tool_call_req' ||
            event.type === 'tool_call_resp' ||
            event.type === 'content'
          ) {
            if (currentSegmentType !== event.type) {
              // Finalize previous segment by changing ID from __streaming__ prefix
              if (currentStreamingId) {
                const finishedId = currentStreamingId
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === finishedId
                      ? { ...m, id: `${m.type}-${Date.now()}-${Math.random()}` }
                      : m,
                  ),
                )
              }

              currentSegmentType = event.type
              currentStreamingId = `${STREAMING_MESSAGE_ID}-${event.type}-${Date.now()}`
              const newSegment: ChatMessage = {
                id: currentStreamingId,
                role: 'assistant',
                type: event.type,
                content: '',
              }
              setMessages((prev) => [...prev, newSegment])
            }

            if (currentStreamingId) {
              let delta = ''
              if (event.type === 'tool_call_req' || event.type === 'tool_call_resp') {
                if (event.data) {
                  delta = typeof event.data === 'string' ? event.data : JSON.stringify(event.data)
                } else if (event.delta) {
                  delta = event.delta
                }
              } else {
                delta = event.delta || ''
              }

              if (delta) {
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id === currentStreamingId) {
                      // For tool calls, if we get a full object, we might want to replace rather than append
                      // because the backend logic for tool calls often emits the full state in one chunk.
                      const isTool = event.type === 'tool_call_req' || event.type === 'tool_call_resp'
                      return { 
                        ...m, 
                        content: isTool ? delta : (m.content + delta) 
                      }
                    }
                    return m
                  }),
                )
              }
            }
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
