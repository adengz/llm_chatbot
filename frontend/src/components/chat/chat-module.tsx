import { useEffect, useRef, useState } from 'react'

import {
  listConversationsConversationsGet,
  listLlmsModelsGet,
  listMessagesConversationsConversationIdMessagesGet,
} from '../../client/sdk.gen'
import type { Conversation as ApiConversation, Message as ApiMessage } from '../../client/types.gen'
import { streamMessage } from '../../client/stream'
import { Badge } from '../ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { ChatComposer } from './chat-composer'
import { ChatMessageList } from './chat-message-list'
import type { ChatMessage, ModelSource, ReasoningEffort } from './chat-types'
import { ConversationSidebar } from './conversation-sidebar'

const STREAMING_MESSAGE_ID = '__streaming__'

function toChatMessage(message: ApiMessage, index: number): ChatMessage {
  return {
    id: `${message.created_at ?? 'message'}-${message.role}-${index}`,
    role: message.role,
    content: message.content,
  }
}

export function ChatModule() {
  const [draft, setDraft] = useState('')
  const [modelSource, setModelSource] = useState<ModelSource>('ollama_cloud')
  const [model, setModel] = useState('qwen3:32b')
  const [reasoningEffort, setReasoningEffort] =
    useState<ReasoningEffort>('medium')
  const [modelOptionsBySource, setModelOptionsBySource] =
    useState<Record<ModelSource, string[]>>({})
  const [isModelOptionsLoading, setIsModelOptionsLoading] = useState(false)
  const [modelOptionsError, setModelOptionsError] = useState<string | null>(null)
  const [modelOptionsRefreshKey, setModelOptionsRefreshKey] = useState(0)
  const [conversations, setConversations] = useState<ApiConversation[]>([])
  const [isConversationsLoading, setIsConversationsLoading] = useState(false)
  const [conversationsError, setConversationsError] = useState<string | null>(null)
  const [messagesError, setMessagesError] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const skipNextHistoryLoadRef = useRef(false)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages])

  useEffect(() => {
    let isCancelled = false

    const loadConversations = async () => {
      setIsConversationsLoading(true)

      const { data, error } = await listConversationsConversationsGet()

      if (isCancelled) {
        return
      }

      if (error || !Array.isArray(data)) {
        setConversations([])
        setConversationsError('Failed to load conversations.')
        setIsConversationsLoading(false)
        return
      }

      setConversations(data)
      setConversationsError(null)
      setIsConversationsLoading(false)
    }

    void loadConversations()

    return () => {
      isCancelled = true
    }
  }, [])

  const refreshConversations = async (failureMessage: string) => {
    const response = await listConversationsConversationsGet()

    if (response.error || !Array.isArray(response.data)) {
      setConversationsError(failureMessage)
      return
    }

    setConversations(response.data)
    setConversationsError(null)
  }

  useEffect(() => {
    let isCancelled = false

    const loadModels = async () => {
      setIsModelOptionsLoading(true)

      const { data, error } = await listLlmsModelsGet()

      if (isCancelled) {
        return
      }

      if (error || !data || typeof data !== 'object') {
        setModelOptionsBySource({})
        setModelOptionsError('Failed to load models from backend. Model list is unavailable.')
        setIsModelOptionsLoading(false)
        return
      }

      const normalizedModelOptions = Object.entries(data).reduce<Record<string, string[]>>(
        (acc, [source, models]) => {
          if (!Array.isArray(models)) {
            return acc
          }

          const validModels = models.filter(
            (value): value is string => typeof value === 'string' && value.trim().length > 0,
          )

          if (validModels.length > 0) {
            acc[source] = Array.from(new Set(validModels))
          }

          return acc
        },
        {},
      )

      if (Object.keys(normalizedModelOptions).length > 0) {
        setModelOptionsBySource(normalizedModelOptions)
        setModelOptionsError(null)
      } else {
        setModelOptionsBySource({})
        setModelOptionsError('No models returned from backend.')
      }

      setIsModelOptionsLoading(false)
    }

    void loadModels()

    return () => {
      isCancelled = true
    }
  }, [modelOptionsRefreshKey])

  const handleRefreshModels = () => {
    setModelOptionsRefreshKey((k) => k + 1)
  }

  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      setMessagesError(null)
      return
    }

    if (skipNextHistoryLoadRef.current) {
      skipNextHistoryLoadRef.current = false
      return
    }

    let isCancelled = false

    const loadHistory = async () => {
      setMessagesError(null)

      let cursor: string | null | undefined = undefined
      const history: ApiMessage[] = []

      while (true) {
        const response: { data?: ApiMessage[]; error?: unknown } = await listMessagesConversationsConversationIdMessagesGet({
          path: { conversation_id: conversationId },
          query: { cursor, limit: 100 },
        })

        if (isCancelled) {
          return
        }

        if (response.error || !Array.isArray(response.data)) {
          setMessages([])
          setMessagesError('Failed to load conversation history.')
          return
        }

        if (response.data.length === 0) {
          break
        }

        history.push(...response.data)
        cursor = response.data[response.data.length - 1]?.created_at ?? null

        if (!cursor) {
          break
        }
      }

      const chronological = history.reverse().map(toChatMessage)
      setMessages(chronological)
    }

    void loadHistory()

    return () => {
      isCancelled = true
    }
  }, [conversationId])

  useEffect(() => {
    const availableSources = Object.keys(modelOptionsBySource)

    if (availableSources.length === 0) {
      return
    }

    if (!availableSources.includes(modelSource)) {
      const nextSource = availableSources[0]
      const nextModels = modelOptionsBySource[nextSource] ?? []
      setModelSource(nextSource)
      setModel(nextModels[0] ?? '')
      return
    }

    const modelsForSource = modelOptionsBySource[modelSource] ?? []
    if (modelsForSource.length > 0 && !modelsForSource.includes(model)) {
      setModel(modelsForSource[0])
    }
  }, [model, modelOptionsBySource, modelSource])

  const handleSelectConversation = (nextConversationId: string) => {
    if (isStreaming || nextConversationId === conversationId) {
      return
    }

    setConversationId(nextConversationId)
  }

  const handleStartNewConversation = () => {
    if (isStreaming) {
      return
    }

    setConversationId(null)
    setMessages([])
    setMessagesError(null)
  }

  const handleStopStreaming = () => {
    abortRef.current?.abort()
  }

  const handleSendClick = async () => {
    const content = draft.trim()
    if (!content || isStreaming) return

    setDraft('')
    setIsStreaming(true)
    setMessagesError(null)

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
    }
    setMessages((prev) => [...prev, userMessage])

    const streamingMessage: ChatMessage = {
      id: STREAMING_MESSAGE_ID,
      role: 'assistant',
      content: '',
    }
    setMessages((prev) => [...prev, streamingMessage])

    const abort = new AbortController()
    abortRef.current = abort

    try {
      for await (const event of streamMessage(
        {
          conversation_id: conversationId ?? undefined,
          content,
          model_source: modelSource,
          model,
          reasoning_effort: reasoningEffort,
        },
        abort.signal,
      )) {
        if (event.type === 'metadata') {
          if (!conversationId) {
            skipNextHistoryLoadRef.current = true
            void refreshConversations('Failed to refresh conversations.')
          }
          setConversationId(event.conversation_id)
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
          setMessages((prev) =>
            prev.map((m) =>
              m.id === STREAMING_MESSAGE_ID
                ? { ...m, id: `assistant-${Date.now()}`, content: m.content || `[Error: ${event.exception}]` }
                : m,
            ),
          )
        } else if (event.type === 'done') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === STREAMING_MESSAGE_ID ? { ...m, id: `assistant-${Date.now()}` } : m,
            ),
          )
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setMessagesError((err as Error).message)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === STREAMING_MESSAGE_ID
              ? { ...m, id: `assistant-${Date.now()}`, content: m.content || '[Error: stream failed]' }
              : m,
          ),
        )
      } else {
        // Remove placeholder if aborted with no content
        setMessages((prev) =>
          prev.map((m) =>
            m.id === STREAMING_MESSAGE_ID
              ? { ...m, id: `assistant-${Date.now()}` }
              : m,
          ),
        )
      }
    } finally {
      abortRef.current = null
      setIsStreaming(false)
    }
  }

  return (
    <div className="grid h-screen grid-cols-[280px_1fr] gap-4 bg-background p-4 text-foreground">
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={conversationId}
        isLoading={isConversationsLoading}
        error={conversationsError}
        isStreaming={isStreaming}
        onSelectConversation={handleSelectConversation}
        onStartNewConversation={handleStartNewConversation}
      />

      <Card className="grid h-full grid-rows-[auto_1fr_auto] overflow-hidden">
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Chat Module Sketch</CardTitle>
            <CardDescription>shadcn + Tailwind MVP composition</CardDescription>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline">source: {modelSource}</Badge>
            <Badge variant="secondary">reasoning: {reasoningEffort}</Badge>
          </div>
        </CardHeader>

        <CardContent className="overflow-y-auto" ref={scrollRef}>
          {messagesError && (
            <p className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {messagesError}
            </p>
          )}
          <ChatMessageList messages={messages} />
        </CardContent>

        <ChatComposer
          draft={draft}
          modelSource={modelSource}
          model={model}
          modelOptionsBySource={modelOptionsBySource}
          isModelOptionsLoading={isModelOptionsLoading}
          modelOptionsError={modelOptionsError}
          reasoningEffort={reasoningEffort}
          isStreaming={isStreaming}
          onDraftChange={setDraft}
          onModelSourceChange={setModelSource}
          onModelChange={setModel}
          onReasoningEffortChange={setReasoningEffort}
          onSendClick={() => { void handleSendClick() }}
          onStopClick={handleStopStreaming}
          onRefreshModels={handleRefreshModels}
        />
      </Card>
    </div>
  )
}
